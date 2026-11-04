package com.twist.mediabridge.contacts;

import android.app.Activity;
import android.content.ContentUris;
import android.content.Intent;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageManager;
import android.database.Cursor;
import android.net.Uri;
import android.os.Build;
import android.os.ParcelFileDescriptor;
import android.provider.DocumentsContract;
import android.provider.ContactsContract;
import android.util.Base64;
import java.io.*;
import java.net.*;
import java.security.MessageDigest;
import java.security.cert.X509Certificate;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;
import java.lang.ref.WeakReference;
import javax.net.ssl.*;
import org.json.*;

/** Phone-initiated, pinned HTTPS; no debugging shell and no cloud service. */
final class LocalLink {
    final android.content.Context context;
    volatile WeakReference<MainActivity> owner;
    final String host, fingerprint;
    final int port;
    volatile String token;
    volatile boolean running = true;
    final Map<String,Uri> files = new ConcurrentHashMap<>();
    final Map<String,JSONObject> metadata = new ConcurrentHashMap<>();
    final List<Uri> roots;
    final SSLSocketFactory sockets;
    final Map<String,File> uploads = new ConcurrentHashMap<>();
    final Map<String,JSONObject> uploadInfo = new ConcurrentHashMap<>();
    final Set<String> installRequests=Collections.newSetFromMap(new ConcurrentHashMap<String,Boolean>());
    final LinkedHashMap<String,JSONObject> completed = new LinkedHashMap<>();
    final ConnectionHealth health=new ConnectionHealth(()->android.os.SystemClock.elapsedRealtime());

    LocalLink(MainActivity activity, Uri uri, List<Uri> folders) throws Exception {
        context=activity.getApplicationContext();owner=new WeakReference<>(activity);
        if (!"twistbridge".equals(uri.getScheme()) || !"connect".equals(uri.getHost())) throw new Exception("Use the pairing link shown on your PC");
        host = uri.getQueryParameter("host");
        if (host == null || !host.matches("[0-9]{1,3}(\\.[0-9]{1,3}){3}")) throw new Exception("Invalid PC address");
        InetAddress address = InetAddress.getByName(host);
        if (address.isLoopbackAddress() || address.isMulticastAddress() || address.isAnyLocalAddress()) throw new Exception("Choose a local PC address");
        port = Integer.parseInt(uri.getQueryParameter("port"));
        if (port < 1 || port > 65535) throw new Exception("Invalid port");
        fingerprint = uri.getQueryParameter("fingerprint");
        token = uri.getQueryParameter("token");
        if (fingerprint == null || !fingerprint.matches("[0-9a-f]{64}") || token == null || !token.matches("[0-9a-f]{64}")) throw new Exception("Invalid or incomplete pairing link");
        roots = new ArrayList<>(folders);
        TrustManager[] trust = {new X509TrustManager() {
            public X509Certificate[] getAcceptedIssuers() { return new X509Certificate[0]; }
            public void checkClientTrusted(X509Certificate[] chain, String auth) throws java.security.cert.CertificateException { throw new java.security.cert.CertificateException("Client certificate unexpected"); }
            public void checkServerTrusted(X509Certificate[] chain, String auth) throws java.security.cert.CertificateException {
                try {
                    if (chain.length != 1 || !MessageDigest.isEqual(hex(MessageDigest.getInstance("SHA-256").digest(chain[0].getEncoded())).getBytes("UTF-8"), fingerprint.getBytes("UTF-8")))
                        throw new Exception("PC certificate does not match pairing link");
                    chain[0].checkValidity();
                } catch (Exception error) { throw new java.security.cert.CertificateException("PC identity verification failed", error); }
            }
        }};
        SSLContext context = SSLContext.getInstance("TLS");
        context.init(null, trust, new java.security.SecureRandom());
        sockets = context.getSocketFactory();
    }

    static String hex(byte[] data) {
        StringBuilder value = new StringBuilder();
        for (byte b : data) value.append(String.format(Locale.US,"%02x", b & 255));
        return value.toString();
    }

    static class SessionEnded extends NetworkRetry.Terminal { SessionEnded(){super("PC session ended. Pair again using a fresh QR code.");} }
    static class RequestGone extends NetworkRetry.Terminal { RequestGone(){super("PC request canceled");} }

    JSONObject postOnce(String route, JSONObject body) throws Exception {
        HttpsURLConnection connection = (HttpsURLConnection)new URL("https",host,port,route).openConnection();
        try {
            connection.setSSLSocketFactory(sockets);
            // The certificate fingerprint is pinned above; it deliberately has no DNS identity.
            connection.setHostnameVerifier((name, session) -> host.equals(name));
            connection.setInstanceFollowRedirects(false);
            connection.setConnectTimeout("/heartbeat".equals(route)?1500:2000); connection.setReadTimeout("/heartbeat".equals(route)?1500:8000);
            connection.setRequestMethod("POST"); connection.setDoOutput(true);
            connection.setRequestProperty("Authorization", "Bearer " + token);
            connection.setRequestProperty("Content-Type", "application/json");
            byte[] bytes = body.toString().getBytes("UTF-8");
            connection.setFixedLengthStreamingMode(bytes.length);
            try (OutputStream out = connection.getOutputStream()) { out.write(bytes); }
            int response=connection.getResponseCode();
            if(response==403)throw new SessionEnded();
            if(response==409)throw new RequestGone();
            if(response!=200)throw new IOException("PC request did not complete");
            ByteArrayOutputStream result = new ByteArrayOutputStream();
            try (InputStream in = connection.getInputStream()) {
                byte[] chunk = new byte[16384]; int size;
                while ((size = in.read(chunk)) != -1) {
                    if (result.size()+size > 32*1024*1024) throw new IOException("Response too large");
                    result.write(chunk,0,size);
                }
            }
            JSONObject value=new JSONObject(result.toString("UTF-8"));
            health.success();
            return value;
        } finally { connection.disconnect(); }
    }

    JSONObject post(String route,JSONObject body)throws Exception {
        // Enrollment is one-use and must never be retried after an uncertain result.
        if("/join".equals(route))return postOnce(route,body);
        return NetworkRetry.run(()->postOnce(route,body),()->running,delay->Thread.sleep(delay));
    }

    void attach(MainActivity activity){owner=new WeakReference<>(activity);}
    void status(String message){MainActivity activity=owner.get();if(activity!=null && !activity.isDestroyed())activity.linkStatus(message);}

    void start() {
        new Thread(() -> {
            try {
                JSONObject identity = new JSONObject().put("model", Build.MANUFACTURER + " " + Build.MODEL);
                token = post("/join", identity).getString("token");
                status("Connected to PC. Approved folders and contacts are ready.\nAn active connection notification keeps this session running.");
                new Thread(() -> {
                    while (running) {
                        try { Thread.sleep(3000); if (running) post("/heartbeat",new JSONObject()); }
                        catch (Exception error) {
                            if(running && (terminal(error) || !health.recent())){
                                status("Connection interrupted: "+safeError(error));stop();
                            }
                        }
                    }
                }, "TwistHeartbeat").start();

                while (running) {
                    JSONObject response;
                    try{response=post("/poll",new JSONObject());}
                    catch(IOException error){
                        if(terminal(error) || !health.recent())throw error;
                        Thread.sleep(250);continue;
                    }
                    JSONObject job = response.optJSONObject("job");
                    if (job == null) continue;
                    String id=job.getString("id");
                    JSONObject result=completed.get(id);
                    if(result==null){
                        result=new JSONObject();
                        try { result.put("value", execute(job.getString("operation"),job.getJSONObject("arguments"))); }
                        catch (Exception error) { result.put("error",safeError(error)); }
                        if(result.toString().length()<2*1024*1024)completed.put(id,result);
                        while(completed.size()>8)completed.remove(completed.keySet().iterator().next());
                    }
                    if (running) {
                        try { post("/result",new JSONObject().put("id",job.getString("id")).put("result",result)); }
                        catch (RequestGone expired) { /* Canceled PC request; continue the same session. */ }
                        catch(IOException error){
                            if(terminal(error) || !health.recent())throw error;
                            // Keep the completed result for redelivery; never repeat a mutation.
                        }
                    }
                }
            } catch (Exception error) {
                if (running) status("Disconnected: "+safeError(error)+"\nPair again on the PC to reconnect.");
            } finally { stop(); }
        },"TwistLocalLink").start();
    }

    String safeError(Exception error) {
        if (error instanceof SecurityException) return "Permission needed. Allow contacts access or choose a media folder on the phone.";
        return error.getMessage() == null ? "Phone could not complete this request" : error.getMessage();
    }

    boolean terminal(Exception error){return error instanceof NetworkRetry.Terminal || NetworkRetry.certificateFailure(error);}

    synchronized void stop() {
        running = false;
        files.clear(); metadata.clear();
        for (File file : uploads.values()) file.delete();
        uploads.clear(); uploadInfo.clear();
        for(String id:installRequests){
            InstallActivity.Request job=InstallActivity.requests.remove(id);
            if(job!=null){job.result("failed","PC disconnected; installation request ended.");job.clean(context);}
        }
        installRequests.clear();
        LinkService.finish(this);
    }

    void disconnect() {
        running = false;
        status("Disconnected. PC access has ended.");
        new Thread(() -> { try { post("/disconnect",new JSONObject()); } catch (Exception ignored) {} finally { stop(); } },"TwistDisconnect").start();
    }

    void listTree(Uri tree, String document, String prefix, JSONArray result, int depth, Set<String> visited) throws Exception {
        if (!running) throw new IOException("Disconnected");
        if (depth > 48 || !visited.add(tree.toString()+"|"+document)) return;
        Uri children = DocumentsContract.buildChildDocumentsUriUsingTree(tree,document);
        String[] columns = {"document_id","_display_name","mime_type","_size","last_modified"};
        try (Cursor cursor = context.getContentResolver().query(children, columns,null,null,null)) {
            while (cursor != null && cursor.moveToNext()) {
                String name = cursor.getString(1);
                if (name == null || name.startsWith(".") || name.contains("/") || name.contains("\\") || name.equals("..")) continue;
                String path = prefix + "/" + name;
                if (DocumentsContract.Document.MIME_TYPE_DIR.equals(cursor.getString(2))) {
                    listTree(tree,cursor.getString(0),path,result,depth+1,visited);
                } else {
                    if (result.length() >= 100000) throw new IOException("Folder contains too many files. Choose a smaller folder.");
                    long size = cursor.getLong(3);
                    if (size < 0) continue;
                    Uri file = DocumentsContract.buildDocumentUriUsingTree(tree,cursor.getString(0));
                    if (files.putIfAbsent(path,file) != null) throw new IOException("Duplicate folder names. Choose folders with different names.");
                    JSONObject row = new JSONObject().put("path",path).put("size",size).put("modified",cursor.getLong(4));
                    metadata.put(path,row); result.put(row);
                }
            }
        }
    }

    Uri selected(String path) throws Exception {
        Uri uri = files.get(path);
        if (uri == null) throw new IOException("File not in current approved listing. Reload albums.");
        return uri;
    }

    String hash(Uri uri) throws Exception {
        MessageDigest hash = MessageDigest.getInstance("SHA-256");
        try (InputStream in = context.getContentResolver().openInputStream(uri)) {
            byte[] chunk = new byte[1024*1024]; int size;
            while ((size=in.read(chunk))!=-1) { if (!running) throw new IOException("Disconnected"); hash.update(chunk,0,size); }
        }
        return hex(hash.digest());
    }

    Object execute(String operation, JSONObject args) throws Exception {
        if (!running) throw new IOException("Disconnected");
        if ("files".equals(operation)) {
            files.clear(); metadata.clear();
            if (roots.isEmpty()) throw new IOException("On the phone choose at least one media folder, then reconnect.");
            JSONArray result = new JSONArray(); Set<String> visited = new HashSet<>();
            for (Uri tree : roots) {
                String id = DocumentsContract.getTreeDocumentId(tree);
                Uri uri = DocumentsContract.buildDocumentUriUsingTree(tree,id);
                String prefix = "Phone";
                try (Cursor c = context.getContentResolver().query(uri,new String[]{"_display_name"},null,null,null)) { if (c!=null && c.moveToFirst()) prefix=c.getString(0); }
                listTree(tree,id,prefix,result,0,visited);
            }
            return result;
        }
        if ("info".equals(operation)) {
            String path=args.getString("path"); Uri uri=selected(path);
            JSONObject result=new JSONObject(metadata.get(path).toString());
            return result.put("sha256",hash(uri));
        }
        if ("read".equals(operation)) {
            Uri uri=selected(args.getString("path"));
            long offset=args.getLong("offset"); int size=args.getInt("size");
            if (offset<0 || size<1 || size>512*1024) throw new IOException("Invalid read range");
            byte[] data=new byte[size]; int used=0;
            try (ParcelFileDescriptor.AutoCloseInputStream in=new ParcelFileDescriptor.AutoCloseInputStream(context.getContentResolver().openFileDescriptor(uri,"r"))) {
                in.getChannel().position(offset);
                while (used<size) { int count=in.read(data,used,size-used); if(count<0)break; used+=count; }
            }
            return Base64.encodeToString(Arrays.copyOf(data,used),Base64.NO_WRAP);
        }
        if ("thumbnail".equals(operation)) {
            String path=args.getString("path");Uri uri=selected(path);
            android.graphics.Bitmap bitmap=null;
            if(Build.VERSION.SDK_INT>=29) {
                bitmap=context.getContentResolver().loadThumbnail(uri,new android.util.Size(256,256),null);
            } else if(path.toLowerCase(Locale.US).matches(".*\\.(mp4|mov|mkv|avi|webm|3gp|m4v)$")) {
                android.media.MediaMetadataRetriever retriever=new android.media.MediaMetadataRetriever();
                try {retriever.setDataSource(context,uri);bitmap=Build.VERSION.SDK_INT>=27?retriever.getScaledFrameAtTime(0,android.media.MediaMetadataRetriever.OPTION_CLOSEST_SYNC,256,256):retriever.getFrameAtTime(0,android.media.MediaMetadataRetriever.OPTION_CLOSEST_SYNC);}
                finally {retriever.release();}
            } else {
                android.graphics.BitmapFactory.Options options=new android.graphics.BitmapFactory.Options();options.inJustDecodeBounds=true;
                try(InputStream in=context.getContentResolver().openInputStream(uri)){android.graphics.BitmapFactory.decodeStream(in,null,options);}
                options.inSampleSize=1;while(Math.max(options.outWidth,options.outHeight)/options.inSampleSize>512)options.inSampleSize*=2;
                options.inJustDecodeBounds=false;
                try(InputStream in=context.getContentResolver().openInputStream(uri)){bitmap=android.graphics.BitmapFactory.decodeStream(in,null,options);}
            }
            if(bitmap==null)throw new IOException("Thumbnail unavailable; click to preview original");
            try{
                float ratio=Math.min(1f,256f/Math.max(bitmap.getWidth(),bitmap.getHeight()));
                android.graphics.Bitmap scaled=android.graphics.Bitmap.createScaledBitmap(bitmap,Math.max(1,(int)(bitmap.getWidth()*ratio)),Math.max(1,(int)(bitmap.getHeight()*ratio)),true);
                ByteArrayOutputStream out=new ByteArrayOutputStream();scaled.compress(android.graphics.Bitmap.CompressFormat.JPEG,85,out);
                if(scaled!=bitmap)scaled.recycle();return Base64.encodeToString(out.toByteArray(),Base64.NO_WRAP);
            }finally{bitmap.recycle();}
        }
        if ("contacts".equals(operation) || "vcard".equals(operation)) {
            Uri.Builder uri=Uri.parse("content://com.twist.mediabridge.contacts/"+operation).buildUpon();
            if ("vcard".equals(operation)) uri.appendPath(args.getString("contact_id")).appendQueryParameter("lookup",args.getString("lookup"));
            else uri.appendQueryParameter("offset",Integer.toString(args.optInt("offset",0)));
            try (Cursor cursor=context.getContentResolver().query(uri.build(),null,null,null,null)) {
                if(cursor==null || !cursor.moveToFirst())throw new IOException("Contacts access unavailable");
                String payload=cursor.getString(0);
                if("vcard".equals(operation))return payload;
                return new JSONArray(new String(Base64.decode(payload,Base64.DEFAULT),"UTF-8"));
            }
        }
        if ("delete_contact".equals(operation)) {
            Uri uri=Uri.parse("content://com.twist.mediabridge.contacts/contacts/"+args.getString("contact_id")).buildUpon().appendQueryParameter("lookup",args.getString("lookup")).build();
            return context.getContentResolver().delete(uri,null,null)>0;
        }
        if ("delete_media".equals(operation)) {
            String path=args.getString("path"); Uri uri=selected(path);
            if(!path.toLowerCase(Locale.US).matches(".*\\.(jpg|jpeg|png|gif|webp|heic|heif|dng|bmp|mp4|mov|mkv|avi|webm|3gp|m4v)$"))throw new IOException("Select photos or videos only");
            boolean deleted=DocumentsContract.deleteDocument(context.getContentResolver(),uri);
            if(deleted){files.remove(path);metadata.remove(path);}return deleted;
        }
        if ("apps".equals(operation)) {
            JSONArray result=new JSONArray(); PackageManager pm=context.getPackageManager();
            for(ApplicationInfo app:pm.getInstalledApplications(0)) {
                if((app.flags&ApplicationInfo.FLAG_SYSTEM)!=0)continue;
                String name=pm.getApplicationLabel(app).toString();
                result.put(new JSONObject().put("id",app.packageName).put("name",name).put("detail",app.packageName).put("label_available",true));
            }
            return result;
        }
        if ("app_files".equals(operation)) {
            ApplicationInfo app=context.getPackageManager().getApplicationInfo(args.getString("package"),0);
            if((app.flags&ApplicationInfo.FLAG_SYSTEM)!=0)throw new IOException("User apps only");
            ArrayList<String> paths=new ArrayList<>(); paths.add(app.sourceDir);
            if(app.splitSourceDirs!=null)paths.addAll(Arrays.asList(app.splitSourceDirs));
            JSONArray result=new JSONArray(); int index=0;
            for(String path:paths) {
                File file=new File(path); String key="Apps/"+app.packageName+"/"+(index++==0?"base.apk":"split-"+index+".apk");
                files.put(key,Uri.fromFile(file));
                JSONObject row=new JSONObject().put("path",key).put("size",file.length()).put("modified",file.lastModified());
                metadata.put(key,row);result.put(row);
            }
            return result;
        }
        if ("install_prepare".equals(operation)) {
            MainActivity activity=owner.get();
            if(activity==null || activity.isFinishing() || !activity.hasWindowFocus())throw new IOException("Open Twist Companion on the phone, then try installation again.");
            for(InstallActivity.Request old:InstallActivity.requests.values()){
                if(!old.released && android.os.SystemClock.elapsedRealtime()-old.created<300000)throw new IOException("Finish or cancel the pending installation on the phone first.");
                old.clean(context);InstallActivity.requests.remove(old.id);
            }
            JSONArray ids=args.getJSONArray("ids");
            if(ids.length()<1 || ids.length()>500)throw new IOException("Invalid APK set");
            ArrayList<File> staged=new ArrayList<>();Set<String> unique=new HashSet<>();
            for(int i=0;i<ids.length();i++){
                String id=ids.getString(i);File file=uploads.get(id);JSONObject info=uploadInfo.get(id);
                if(!unique.add(id) || file==null || info==null || !info.optBoolean("install") || file.length()!=info.getLong("size") || !hash(Uri.fromFile(file)).equals(info.getString("sha256")))throw new IOException("APK upload integrity check failed");
                staged.add(file);
            }
            InstallActivity.Request job=new InstallActivity.Request(staged);InstallActivity.requests.put(job.id,job);
            installRequests.add(job.id);
            new android.os.Handler(android.os.Looper.getMainLooper()).postDelayed(()->{
                if(!job.released){job.result("failed","Installation approval expired.");job.clean(context);}
            },300000);
            for(String id:unique){uploads.remove(id);uploadInfo.remove(id);}
            activity.runOnUiThread(()->{
                try{activity.startActivity(new Intent(activity,InstallActivity.class).putExtra("request",job.id));}
                catch(Exception error){job.result("failed","Open Twist Companion on the phone and try again.");job.clean(context);}
            });
            return job.id;
        }
        if ("install_status".equals(operation) || "install_release".equals(operation)) {
            String id=args.getString("id");
            InstallActivity.Request job=installRequests.contains(id)?InstallActivity.requests.get(id):null;
            if(job==null)throw new IOException("Installation request expired; update Twist Companion to 1.5 if needed.");
            if("install_release".equals(operation)){job.clean(context);InstallActivity.requests.remove(job.id);installRequests.remove(job.id);return true;}
            return job.snapshot();
        }
        if ("upload_begin".equals(operation) || "install_upload_begin".equals(operation)) {
            boolean install="install_upload_begin".equals(operation);
            if(!install && roots.isEmpty())throw new IOException("Choose a receive folder on the phone before connecting.");
            args.put("install",install);
            String path=args.getString("path");
            if(install && !path.matches("part-[0-9]+\\.apk"))throw new IOException("Select APK installation files only");
            if(path.length()>1024 || path.startsWith("/") || path.contains("\\"))throw new IOException("Invalid destination");
            for(String part:path.split("/",-1))if(part.isEmpty()||part.equals(".")||part.equals("..")||part.startsWith("."))throw new IOException("Invalid destination");
            long size=args.getLong("size");String sha=args.getString("sha256");
            if(size<0 || size>8L*1024*1024*1024 || !sha.matches("[0-9a-f]{64}"))throw new IOException("Invalid file metadata");
            if(size>context.getCacheDir().getUsableSpace()-16*1024*1024)throw new IOException("Not enough temporary space on phone");
            String id=UUID.randomUUID().toString();File file=File.createTempFile("twist-upload-",".part",context.getCacheDir());
            uploads.put(id,file);uploadInfo.put(id,args);return id;
        }
        if ("upload_chunk".equals(operation)) {
            File file=uploads.get(args.getString("id"));JSONObject info=uploadInfo.get(args.getString("id"));
            if(file==null || info==null)throw new IOException("Upload no longer active");
            byte[] chunk=Base64.decode(args.getString("data"),Base64.DEFAULT);
            if(chunk.length>512*1024 || file.length()!=args.getLong("offset") || file.length()+chunk.length>info.getLong("size"))throw new IOException("Invalid upload range");
            try(FileOutputStream out=new FileOutputStream(file,true)){out.write(chunk);}return true;
        }
        if ("upload_abort".equals(operation)) {
            File file=uploads.remove(args.getString("id"));uploadInfo.remove(args.getString("id"));if(file!=null)file.delete();return true;
        }
        if ("upload_finish".equals(operation)) {
            String id=args.getString("id");File file=uploads.get(id);JSONObject info=uploadInfo.get(id);
            if(file==null || info==null)throw new IOException("Upload no longer active");
            if(info.optBoolean("install"))throw new IOException("Use Android installer for APK staging");
            if(file.length()!=info.getLong("size") || !hash(Uri.fromFile(file)).equals(info.getString("sha256")))throw new IOException("Upload failed checksum verification");
            Uri tree=roots.get(0);Uri parent=DocumentsContract.buildDocumentUriUsingTree(tree,DocumentsContract.getTreeDocumentId(tree));
            String[] parts=info.getString("path").split("/");
            for(int i=0;i<parts.length-1;i++){
                Uri child=child(tree,parent,parts[i]);
                if(child==null)child=DocumentsContract.createDocument(context.getContentResolver(),parent,DocumentsContract.Document.MIME_TYPE_DIR,parts[i]);
                if(child==null)throw new IOException("Cannot create destination folder");parent=child;
            }
            String name=parts[parts.length-1];Uri existing=child(tree,parent,name);
            if(existing!=null){if(hash(existing).equals(info.getString("sha256"))){uploads.remove(id);uploadInfo.remove(id);file.delete();return "already present";}throw new IOException("Different content already exists. Nothing overwritten.");}
            String extension=android.webkit.MimeTypeMap.getFileExtensionFromUrl(name).toLowerCase(Locale.US);
            String mime=android.webkit.MimeTypeMap.getSingleton().getMimeTypeFromExtension(extension);
            Uri stage=DocumentsContract.createDocument(context.getContentResolver(),parent,mime==null?"application/octet-stream":mime,".twist-"+id);
            if(stage==null)throw new IOException("Cannot create destination file");
            try {
                try(InputStream in=new FileInputStream(file);OutputStream out=context.getContentResolver().openOutputStream(stage,"w")){
                    byte[] chunk=new byte[1024*1024];int size;while((size=in.read(chunk))!=-1){if(!running)throw new IOException("Disconnected");out.write(chunk,0,size);}
                }
                if(!hash(stage).equals(info.getString("sha256")))throw new IOException("Destination checksum mismatch");
                if(child(tree,parent,name)!=null)throw new IOException("Destination appeared during transfer. Nothing overwritten.");
                Uri published=DocumentsContract.renameDocument(context.getContentResolver(),stage,name);
                if(published==null)throw new IOException("Could not publish completed file");
                stage=null;uploads.remove(id);uploadInfo.remove(id);file.delete();return "copied";
            } finally {if(stage!=null)try{DocumentsContract.deleteDocument(context.getContentResolver(),stage);}catch(Exception ignored){}}
        }
        throw new IOException("This action needs USB or Android wireless debugging in this release.");
    }

    Uri child(Uri tree,Uri parent,String name)throws Exception{
        Uri children=DocumentsContract.buildChildDocumentsUriUsingTree(tree,DocumentsContract.getDocumentId(parent));
        try(Cursor c=context.getContentResolver().query(children,new String[]{"document_id","_display_name"},null,null,null)){
            while(c!=null && c.moveToNext())if(name.equals(c.getString(1)))return DocumentsContract.buildDocumentUriUsingTree(tree,c.getString(0));
        }return null;
    }
}

