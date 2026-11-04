package com.twist.mediabridge.contacts;
import java.io.IOException;
import javax.net.ssl.SSLHandshakeException;
import java.security.cert.CertificateException;
import javax.net.ssl.SSLPeerUnverifiedException;

/** Bounded retries only for transport failures; trust/session failures are final. */
final class NetworkRetry {
    interface Operation<T>{T run()throws Exception;}
    interface Running{boolean get();}
    interface Pause{void sleep(long milliseconds)throws InterruptedException;}
    static class Terminal extends IOException{Terminal(String message){super(message);}}
    static <T>T run(Operation<T> operation,Running running,Pause pause)throws Exception{
        for(int attempt=0;;attempt++){
            try{return operation.run();}
            catch(IOException temporary){
                if(temporary instanceof Terminal || certificateFailure(temporary) || !running.get() || attempt>=2)throw temporary;
                pause.sleep(250L*(attempt+1));
            }
        }
    }
    static boolean certificateFailure(Throwable error){
        for(int depth=0;error!=null && depth<20;depth++,error=error.getCause())
            if(error instanceof CertificateException || error instanceof SSLPeerUnverifiedException)return true;
        return false;
    }
}
