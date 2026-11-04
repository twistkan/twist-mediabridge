package com.twist.mediabridge.contacts;
import java.io.IOException;
import javax.net.ssl.SSLHandshakeException;
public class NetworkRetryCheck{
    public static void main(String[]args)throws Exception{
        int[] attempts={0};long[] delay={0};
        String value=NetworkRetry.run(()->{if(++attempts[0]<3)throw new IOException("temporary");return "ok";},()->true,ms->delay[0]+=ms);
        if(!"ok".equals(value)||attempts[0]!=3||delay[0]!=750)throw new AssertionError("Transient retry failed");
        attempts[0]=0;
        try{NetworkRetry.run(()->{attempts[0]++;SSLHandshakeException error=new SSLHandshakeException("untrusted");error.initCause(new java.security.cert.CertificateException("pin mismatch"));throw error;},()->true,ms->{});throw new AssertionError();}
        catch(SSLHandshakeException expected){if(attempts[0]!=1)throw new AssertionError("Certificate failure retried");}
        attempts[0]=0;
        value=NetworkRetry.run(()->{if(++attempts[0]<3)throw new SSLHandshakeException("connection reset during handshake");return "ok";},()->true,ms->{});
        if(!"ok".equals(value)||attempts[0]!=3)throw new AssertionError("Transport handshake failure not recovered");
        attempts[0]=0;
        try{NetworkRetry.run(()->{attempts[0]++;throw new NetworkRetry.Terminal("session ended");},()->true,ms->{});throw new AssertionError();}
        catch(NetworkRetry.Terminal expected){if(attempts[0]!=1)throw new AssertionError("Ended session retried");}
        attempts[0]=0;
        try{NetworkRetry.run(()->{attempts[0]++;throw new IOException("offline");},()->true,ms->{});throw new AssertionError();}
        catch(IOException expected){if(attempts[0]!=3)throw new AssertionError("Retries not bounded");}
        attempts[0]=0;
        try{NetworkRetry.run(()->{attempts[0]++;throw new IOException("closed");},()->false,ms->{});throw new AssertionError();}
        catch(IOException expected){if(attempts[0]!=1)throw new AssertionError("Canceled session retried");}
        System.out.println("Android retry policy: transient recovery, bounded failures, certificate/session rejection and cancellation passed");
    }
}
