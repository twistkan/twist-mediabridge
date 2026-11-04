package com.twist.mediabridge.contacts;

import android.app.*;
import android.content.*;
import android.os.*;
import android.net.wifi.WifiManager;

/** User-visible connection lifetime, with CPU/Wi-Fi locks only while connected. */
public class LinkService extends Service {
    static volatile LocalLink active;
    static volatile LinkService instance;
    PowerManager.WakeLock cpu;
    WifiManager.WifiLock wifi;
    LocalLink owned;

    static void begin(MainActivity activity,LocalLink link){
        LocalLink old=active;
        if(old!=null && old!=link)old.disconnect();
        active=link;
        Intent intent=new Intent(activity,LinkService.class);
        try{if(Build.VERSION.SDK_INT>=26)activity.startForegroundService(intent);else activity.startService(intent);}
        catch(RuntimeException error){link.stop();throw error;}
    }
    static void finish(LocalLink link){
        new Handler(Looper.getMainLooper()).post(()->{
            if(active!=link)return;
            active=null;
            LinkService service=instance;
            if(service!=null)service.stopSelf();
        });
    }
    public void onCreate(){super.onCreate();instance=this;}
    public int onStartCommand(Intent intent,int flags,int id){
        if(intent!=null && "stop".equals(intent.getAction())){
            LocalLink link=active;if(link!=null)link.disconnect();stopSelf();return START_NOT_STICKY;
        }
        if(active==null){stopSelf();return START_NOT_STICKY;}
        owned=active;
        final LocalLink session=owned;
        new Handler(Looper.getMainLooper()).postDelayed(()->{if(active==session)session.disconnect();},6*60*60*1000L);
        NotificationManager manager=(NotificationManager)getSystemService(NOTIFICATION_SERVICE);
        if(Build.VERSION.SDK_INT>=26)manager.createNotificationChannel(new NotificationChannel("twist_connection","PC connection",NotificationManager.IMPORTANCE_LOW));
        int immutable=Build.VERSION.SDK_INT>=23?PendingIntent.FLAG_IMMUTABLE:0;
        PendingIntent open=PendingIntent.getActivity(this,1,new Intent(this,MainActivity.class),PendingIntent.FLAG_UPDATE_CURRENT|immutable);
        PendingIntent stop=PendingIntent.getService(this,2,new Intent(this,LinkService.class).setAction("stop"),PendingIntent.FLAG_UPDATE_CURRENT|immutable);
        Notification.Builder builder=Build.VERSION.SDK_INT>=26?new Notification.Builder(this,"twist_connection"):new Notification.Builder(this);
        Notification notification=builder.setSmallIcon(android.R.drawable.stat_sys_upload)
            .setContentTitle("Twist Companion connection active")
            .setContentText("Connected to your PC. Tap Disconnect to end access.")
            .setContentIntent(open).setOngoing(true).addAction(android.R.drawable.ic_menu_close_clear_cancel,"Disconnect",stop).build();
        startForeground(42,notification);
        if(cpu==null){cpu=((PowerManager)getSystemService(POWER_SERVICE)).newWakeLock(PowerManager.PARTIAL_WAKE_LOCK,"Twist:LocalConnection");cpu.setReferenceCounted(false);cpu.acquire(6*60*60*1000L);}
        if(wifi==null){WifiManager wm=(WifiManager)getApplicationContext().getSystemService(WIFI_SERVICE);if(wm!=null){wifi=wm.createWifiLock(WifiManager.WIFI_MODE_FULL_HIGH_PERF,"Twist:LocalConnection");wifi.setReferenceCounted(false);wifi.acquire();}}
        return START_NOT_STICKY;
    }
    public IBinder onBind(Intent intent){return null;}
    public void onTimeout(int startId,int type){LocalLink link=active;if(link!=null)link.disconnect();stopSelf();}
    public void onDestroy(){
        if(instance==this){instance=null;if(active==owned){active=null;if(owned!=null)owned.disconnect();}}
        if(cpu!=null && cpu.isHeld())cpu.release();
        if(wifi!=null && wifi.isHeld())wifi.release();
        stopForeground(true);super.onDestroy();
    }
}
