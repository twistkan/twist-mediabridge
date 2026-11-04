package com.twist.mediabridge.contacts;

/** A failed heartbeat is not a lost connection when authenticated data still flows. */
final class ConnectionHealth {
    interface Clock{long now();}
    final Clock clock;
    volatile long lastSuccess=Long.MIN_VALUE;
    ConnectionHealth(Clock clock){this.clock=clock;}
    void success(){lastSuccess=clock.now();}
    boolean recent(){return lastSuccess!=Long.MIN_VALUE && clock.now()-lastSuccess<12000;}
}
