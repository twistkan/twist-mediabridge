package com.twist.mediabridge.contacts;
import android.app.Activity;
import android.os.Bundle;
import android.content.Intent;
import android.hardware.Camera;
import android.view.*;
import android.widget.*;
import com.google.zxing.*;
import com.google.zxing.common.HybridBinarizer;
import java.util.*;

/** Local QR decoding; camera frames and pairing links are never saved. */
@SuppressWarnings("deprecation")
public class ScanActivity extends Activity implements SurfaceHolder.Callback,Camera.PreviewCallback {
    Camera camera;
    volatile boolean busy=false,done=false;
    long last=0;
    public void onCreate(Bundle state){
        super.onCreate(state);getWindow().addFlags(WindowManager.LayoutParams.FLAG_SECURE|WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        LinearLayout layout=new LinearLayout(this);layout.setOrientation(LinearLayout.VERTICAL);
        TextView text=new TextView(this);text.setText("Scan the QR in PC → Companion Wi-Fi\nOnly scan a code shown by your own PC.");text.setPadding(24,24,24,24);text.setTextSize(18);layout.addView(text);
        SurfaceView surface=new SurfaceView(this);layout.addView(surface,new LinearLayout.LayoutParams(-1,0,1));surface.getHolder().addCallback(this);
        Button cancel=new Button(this);cancel.setText("Cancel");cancel.setOnClickListener(v->finish());layout.addView(cancel);setContentView(layout);
    }
    public void surfaceCreated(SurfaceHolder holder){
        try{camera=Camera.open();camera.setDisplayOrientation(90);Camera.Parameters p=camera.getParameters();
            List<String> modes=p.getSupportedFocusModes();if(modes!=null && modes.contains(Camera.Parameters.FOCUS_MODE_CONTINUOUS_PICTURE))p.setFocusMode(Camera.Parameters.FOCUS_MODE_CONTINUOUS_PICTURE);
            camera.setParameters(p);camera.setPreviewDisplay(holder);camera.setPreviewCallback(this);camera.startPreview();
        }catch(Exception error){Toast.makeText(this,"Cannot open camera. Paste the pairing link instead.",Toast.LENGTH_LONG).show();finish();}
    }
    public void surfaceChanged(SurfaceHolder holder,int format,int width,int height){}
    public void surfaceDestroyed(SurfaceHolder holder){release();}
    void release(){if(camera!=null){camera.setPreviewCallback(null);camera.stopPreview();camera.release();camera=null;}}
    public void onPreviewFrame(byte[] data,Camera source){
        if(done || busy || System.currentTimeMillis()-last<300)return;
        last=System.currentTimeMillis();busy=true;Camera.Size size=source.getParameters().getPreviewSize();byte[] frame=data.clone();
        new Thread(()->{
            try{
                PlanarYUVLuminanceSource luminance=new PlanarYUVLuminanceSource(frame,size.width,size.height,0,0,size.width,size.height,false);
                MultiFormatReader reader=new MultiFormatReader();Map<DecodeHintType,Object> hints=new EnumMap<>(DecodeHintType.class);
                hints.put(DecodeHintType.POSSIBLE_FORMATS,Collections.singletonList(BarcodeFormat.QR_CODE));hints.put(DecodeHintType.TRY_HARDER,Boolean.TRUE);reader.setHints(hints);
                String value=reader.decodeWithState(new BinaryBitmap(new HybridBinarizer(luminance))).getText();
                if(value.startsWith("twistbridge://connect?")){done=true;runOnUiThread(()->{setResult(RESULT_OK,new Intent().putExtra("pairing",value));finish();});}
            }catch(Exception ignored){}finally{busy=false;}
        },"TwistQRDecode").start();
    }
    public void onPause(){done=true;release();super.onPause();}
}
