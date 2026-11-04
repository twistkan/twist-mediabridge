package com.twist.mediabridge.contacts;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.os.Bundle;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.widget.*;
import android.graphics.Color;
import android.view.WindowManager;
import java.util.*;
import java.io.File;

public class MainActivity extends Activity {
    TextView status, folders;
    EditText linkText;
    LocalLink link;
    final ArrayList<Uri> roots = new ArrayList<>();
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        for(android.content.UriPermission permission:getContentResolver().getPersistedUriPermissions())
            if(permission.isReadPermission() && "com.android.externalstorage.documents".equals(permission.getUri().getAuthority()))roots.add(permission.getUri());
        String receive=getPreferences(0).getString("receive","");
        if(!receive.isEmpty()){Uri uri=Uri.parse(receive);if(roots.remove(uri))roots.add(0,uri);}
        if(LinkService.active==null)for(File file:getCacheDir().listFiles()==null?new File[0]:getCacheDir().listFiles())if(file.getName().startsWith("twist-upload-"))file.delete();
        ScrollView scroll=new ScrollView(this);
        LinearLayout layout=new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);layout.setPadding(28,48,28,36);
        layout.setBackgroundColor(Color.rgb(16,14,43));scroll.addView(layout);
        TextView title=text(layout,"Twist Companion · 1.5",26);title.setTextColor(Color.rgb(182,163,255));
        text(layout,"Your phone. Your PC. No cable required.",16);
        status=text(layout,"Ready. Connect over local Wi-Fi, or use the existing USB contacts connection.",16);
        text(layout,"1 · Choose the phone folders your PC may browse. Only local device storage is supported. Choose a receive folder for files sent from the PC.\n2 · Allow contacts access if you want contact backups.\n3 · On PC open Companion Wi-Fi. Tap Scan PC QR below, then approve Connect.\n\nKeep this app open during use. Internet is not required.",15);
        folders=text(layout,"",14);updateFolders();
        button(layout,"Choose media folder",()-> {
            if(link!=null && link.running){linkStatus("Disconnect before changing approved folders.");return;}
            Intent intent=new Intent(Intent.ACTION_OPEN_DOCUMENT_TREE);
            intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION|Intent.FLAG_GRANT_WRITE_URI_PERMISSION|Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION);
            intent.putExtra(Intent.EXTRA_LOCAL_ONLY,true);startActivityForResult(intent,20);
        });
        button(layout,"Choose receive folder",()-> {
            if(link!=null && link.running){linkStatus("Disconnect before changing folders.");return;}
            Intent intent=new Intent(Intent.ACTION_OPEN_DOCUMENT_TREE);
            intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION|Intent.FLAG_GRANT_WRITE_URI_PERMISSION|Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION);
            intent.putExtra(Intent.EXTRA_LOCAL_ONLY,true);startActivityForResult(intent,22);
        });
        button(layout,"Forget approved folders",()-> {
            if(link!=null){link.disconnect();link=null;}
            for(Uri uri:roots)try{getContentResolver().releasePersistableUriPermission(uri,Intent.FLAG_GRANT_READ_URI_PERMISSION|Intent.FLAG_GRANT_WRITE_URI_PERMISSION);}catch(Exception ignored){}
            roots.clear();updateFolders();
        });
        button(layout,"Allow contacts access",()->requestPermissions(new String[]{Manifest.permission.READ_CONTACTS,Manifest.permission.WRITE_CONTACTS},1));
        button(layout,"Scan PC QR",()->{
            if(checkSelfPermission(Manifest.permission.CAMERA)!=PackageManager.PERMISSION_GRANTED)requestPermissions(new String[]{Manifest.permission.CAMERA},2);
            else startActivityForResult(new Intent(this,ScanActivity.class),21);
        });
        text(layout,"Pairing link (fallback: send the PC link to this phone and paste it here)",14);
        linkText=new EditText(this);linkText.setTextColor(Color.WHITE);linkText.setHintTextColor(Color.LTGRAY);
        linkText.setHint("twistbridge://connect?…");linkText.setSingleLine(false);linkText.setSaveEnabled(false);
        linkText.setInputType(android.text.InputType.TYPE_CLASS_TEXT|android.text.InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS);
        layout.addView(linkText);
        button(layout,"Connect to PC",()->approve(linkText.getText().toString().trim()));
        button(layout,"Disconnect",()->{if(link!=null){link.disconnect();link=null;}linkText.setText("");linkStatus("Disconnected. PC session access has ended.");});
        text(layout,"Powered by Tweest\nThe companion requests Android’s network permission for your local connection. It does not upload to a cloud service. USB and Android wireless debugging remain available on the PC.",13);
        setContentView(scroll);
        if(android.os.Build.VERSION.SDK_INT>=33 && checkSelfPermission("android.permission.POST_NOTIFICATIONS")!=PackageManager.PERMISSION_GRANTED)requestPermissions(new String[]{"android.permission.POST_NOTIFICATIONS"},3);
        if(LinkService.active!=null && LinkService.active.running){link=LinkService.active;link.attach(this);linkStatus("PC connection active. Disconnect here to end access.");}
        handle(getIntent());
    }
    TextView text(LinearLayout layout,String value,int size){TextView t=new TextView(this);t.setText(value);t.setTextSize(size);t.setTextColor(Color.rgb(246,244,255));t.setPadding(0,12,0,16);layout.addView(t);return t;}
    void button(LinearLayout layout,String label,Runnable action){Button b=new Button(this);b.setText(label);layout.addView(b);b.setOnClickListener(v->action.run());}
    void updateFolders(){
        StringBuilder value=new StringBuilder("Approved folders: "+roots.size());
        for(int i=0;i<roots.size();i++){
            String id=android.provider.DocumentsContract.getTreeDocumentId(roots.get(i));
            value.append("\n").append(i==0?"Receive + browse: ":"Browse: ").append(id);
        }
        folders.setText(value.toString());
    }
    void linkStatus(String message){runOnUiThread(()->status.setText(message));}
    void handle(Intent intent){if(intent!=null && intent.getData()!=null && "twistbridge".equals(intent.getData().getScheme()))approve(intent.getData().toString());}
    @Override public void onNewIntent(Intent intent){super.onNewIntent(intent);setIntent(intent);handle(intent);}
    void approve(String value){
        try{
            Uri uri=Uri.parse(value);
            if(!"twistbridge".equals(uri.getScheme()) || !"connect".equals(uri.getHost()))throw new Exception("Scan or paste the pairing link from Twist MediaBridge on your PC.");
            String host=uri.getQueryParameter("host");
            new AlertDialog.Builder(this).setTitle("Connect to your PC?")
                .setMessage("Allow PC "+host+" to browse your approved folders and access contacts if permitted?\n\nOnly scan a QR shown by your own PC. Disconnect here to end access.")
                .setNegativeButton("Cancel",(d,w)->linkText.setText(""))
                .setPositiveButton("Connect",(d,w)->{
                    try{if(link!=null)link.disconnect();link=new LocalLink(this,uri,roots);LinkService.begin(this,link);linkText.setText("");setIntent(new Intent());linkStatus("Connecting securely…");link.start();}
                    catch(Exception error){linkStatus("Could not connect: "+error.getMessage());}
                }).show();
        }catch(Exception error){linkStatus(error.getMessage());}
    }
    @Override public void onActivityResult(int request,int result,Intent data){
        super.onActivityResult(request,result,data);
        if(request==21 && result==RESULT_OK && data!=null){approve(data.getStringExtra("pairing"));return;}
        if((request==20 || request==22) && result==RESULT_OK && data!=null){
            Uri uri=data.getData();
            if(uri==null || !"com.android.externalstorage.documents".equals(uri.getAuthority())){linkStatus("Choose a folder in this phone’s local storage.");return;}
            try{int flags=data.getFlags()&(Intent.FLAG_GRANT_READ_URI_PERMISSION|Intent.FLAG_GRANT_WRITE_URI_PERMISSION);getContentResolver().takePersistableUriPermission(uri,flags);if(request==22){roots.remove(uri);roots.add(0,uri);getPreferences(0).edit().putString("receive",uri.toString()).apply();}else if(!roots.contains(uri))roots.add(uri);updateFolders();}
            catch(Exception error){linkStatus("Folder access was not approved.");}
        }
    }
    @Override public void onRequestPermissionsResult(int code,String[] permissions,int[] grants){super.onRequestPermissionsResult(code,permissions,grants);if(code==3)return;if(code==2){if(checkSelfPermission(Manifest.permission.CAMERA)==PackageManager.PERMISSION_GRANTED)startActivityForResult(new Intent(this,ScanActivity.class),21);else linkStatus("Camera permission declined. Paste the PC pairing link instead.");return;}linkStatus(checkSelfPermission(Manifest.permission.READ_CONTACTS)==PackageManager.PERMISSION_GRANTED?"Contacts access approved. Load contacts on the PC after connecting.":"Contacts permission not granted. Media folders can still be used.");}
    @Override public void onDestroy(){super.onDestroy();}
}

