package com.twist.mediabridge.contacts;

import android.app.Activity;
import android.app.PendingIntent;
import android.content.Intent;
import android.content.pm.PackageInstaller;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.widget.*;
import java.io.*;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;
import org.json.JSONObject;

/** Explicit phone approval; never requests privileged or silent installation. */
public class InstallActivity extends Activity {
    static final Map<String,Request> requests=new ConcurrentHashMap<>();
    static class Request {
        final String id=UUID.randomUUID().toString();
        final List<File> files;
        final long created=android.os.SystemClock.elapsedRealtime();
        volatile String status="waiting", message="Approve installation on the phone.";
        int session=-1;
        boolean started=false, released=false;
        Request(List<File> files){this.files=files;}
        synchronized void clean(android.content.Context context){
            released=true;
            if(session>=0)try{context.getPackageManager().getPackageInstaller().abandonSession(session);}catch(Exception ignored){}
            for(File file:files)file.delete();
        }
        synchronized void result(String state,String detail){if(!released){status=state;message=detail;}}
        JSONObject snapshot() throws Exception{return new JSONObject().put("status",status).put("message",message);}
    }
    Request request;
    TextView message;
    @Override public void onCreate(Bundle state){super.onCreate(state);show(getIntent());}
    @Override public void onNewIntent(Intent intent){super.onNewIntent(intent);setIntent(intent);show(intent);}
    void show(Intent intent){
        request=requests.get(intent.getStringExtra("request"));
        if(request==null || request.released){finish();return;}
        LinearLayout layout=new LinearLayout(this);layout.setOrientation(1);layout.setPadding(32,40,32,32);
        message=new TextView(this);message.setTextSize(18);message.setText("Install app sent by your PC?\n\nAndroid will check compatibility and ask you to confirm. Only install files you trust.");layout.addView(message);
        Button approve=new Button(this);approve.setText("Continue to Android installer");layout.addView(approve);approve.setOnClickListener(v->begin());
        Button cancel=new Button(this);cancel.setText("Cancel installation");layout.addView(cancel);cancel.setOnClickListener(v->{request.result("failed","Installation cancelled on the phone.");request.clean(this);finish();});
        setContentView(layout);
        if(intent.hasExtra(PackageInstaller.EXTRA_STATUS)){
            int status=intent.getIntExtra(PackageInstaller.EXTRA_STATUS,PackageInstaller.STATUS_FAILURE);
            if(status==PackageInstaller.STATUS_PENDING_USER_ACTION){
                Intent confirmation=intent.getParcelableExtra(Intent.EXTRA_INTENT);
                try{if(confirmation==null)throw new IOException("Android did not provide an approval screen.");startActivity(confirmation);}
                catch(Exception error){request.result("failed",error.getMessage());}
            }else{
                request.result(status==PackageInstaller.STATUS_SUCCESS?"installed":"failed",
                    status==PackageInstaller.STATUS_SUCCESS?"Android confirmed installation.":"Android installer: "+intent.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE));
                request.clean(this);message.setText(request.message);approve.setEnabled(false);
            }
        }
    }
    void begin(){
        if(request.released || request.started)return;
        if(Build.VERSION.SDK_INT>=26 && !getPackageManager().canRequestPackageInstalls()){
            message.setText("Enable ‘Allow from this source’ for Twist Companion, return here, then tap Continue again.");
            try{startActivity(new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,Uri.parse("package:"+getPackageName())));}
            catch(Exception error){message.setText("Open Settings → Install unknown apps → Twist Companion, then return here.");}
            return;
        }
        request.started=true;message.setText("Preparing Android installer…");
        final Request job=request;
        new Thread(()->{
            try{
                PackageInstaller installer=getPackageManager().getPackageInstaller();
                PackageInstaller.SessionParams params=new PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL);
                if(Build.VERSION.SDK_INT>=31)params.setRequireUserAction(PackageInstaller.SessionParams.USER_ACTION_REQUIRED);
                synchronized(job){if(job.released)return;job.session=installer.createSession(params);}
                try(PackageInstaller.Session session=installer.openSession(job.session)){
                    for(int i=0;i<job.files.size();i++){
                        File file=job.files.get(i);
                        try(InputStream in=new FileInputStream(file);OutputStream out=session.openWrite("part-"+i+".apk",0,file.length())){
                            byte[] buffer=new byte[512*1024];int count;
                            while((count=in.read(buffer))!=-1){if(job.released)throw new IOException("Installation cancelled.");out.write(buffer,0,count);}session.fsync(out);
                        }
                    }
                    Intent callback=new Intent(this,InstallActivity.class).putExtra("request",job.id).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP);
                    int flags=PendingIntent.FLAG_UPDATE_CURRENT;
                    if(Build.VERSION.SDK_INT>=31)flags|=PendingIntent.FLAG_MUTABLE;
                    synchronized(job){if(job.released)return;session.commit(PendingIntent.getActivity(this,job.session,callback,flags).getIntentSender());}
                }
            }catch(Exception error){job.result("failed","Could not install: "+error.getMessage());job.clean(this);runOnUiThread(()->message.setText(job.message));}
        },"twist-installer").start();
    }
    @Override public void onBackPressed(){
        if(request!=null && !request.released){request.result("failed","Installation cancelled on the phone.");request.clean(this);}super.onBackPressed();
    }
}
