package com.twist.mediabridge.contacts;
public class ConnectionHealthCheck{
    public static void main(String[]args){
        long[] now={0};ConnectionHealth health=new ConnectionHealth(()->now[0]);
        if(health.recent())throw new AssertionError("Unpaired connection marked healthy");
        health.success();
        for(int chunk=0;chunk<100;chunk++){
            now[0]+=2000;health.success();now[0]+=1000;
            if(!health.recent())throw new AssertionError("Heartbeat failure ended active bulk traffic");
        }
        now[0]+=12000;
        if(health.recent())throw new AssertionError("Disconnected peer remained healthy");
        System.out.println("Bulk traffic health: missed heartbeats tolerate fresh authenticated data; idle/offline sessions expire");
    }
}
