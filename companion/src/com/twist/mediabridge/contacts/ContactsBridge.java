package com.twist.mediabridge.contacts;

import android.Manifest;
import android.content.ContentProvider;
import android.content.ContentUris;
import android.content.ContentValues;
import android.content.pm.PackageManager;
import android.database.Cursor;
import android.database.MatrixCursor;
import android.net.Uri;
import android.os.Binder;
import android.os.ParcelFileDescriptor;
import android.provider.ContactsContract;
import android.util.Base64;
import java.io.InputStream;
import java.io.ByteArrayOutputStream;
import org.json.JSONArray;
import org.json.JSONObject;

public class ContactsBridge extends ContentProvider {
    public ParcelFileDescriptor openFile(Uri uri, String mode) throws java.io.FileNotFoundException {
        checkCaller();
        require(Manifest.permission.READ_CONTACTS);
        if (!"r".equals(mode) || !"/export".equals(uri.getPath())) throw new java.io.FileNotFoundException("Read-only contact export expected");
        try {
            final JSONArray rows = new JSONArray(uri.getQueryParameter("items"));
            if (rows.length() < 1 || rows.length() > 10) throw new IllegalArgumentException("Export 1-10 contacts per request");
            final ParcelFileDescriptor[] pipe = ParcelFileDescriptor.createReliablePipe();
            new Thread(() -> {
                try (java.io.OutputStream output = new ParcelFileDescriptor.AutoCloseOutputStream(pipe[1])) {
                    for (int index=0; index<rows.length(); index++) {
                        JSONObject row = rows.getJSONObject(index);
                        long id = Long.parseLong(row.getString("contact_id"));
                        String lookup = null;
                        try (Cursor cursor = getContext().getContentResolver().query(ContentUris.withAppendedId(ContactsContract.Contacts.CONTENT_URI,id),new String[]{ContactsContract.Contacts.LOOKUP_KEY},null,null,null)) {
                            if (cursor != null && cursor.moveToFirst()) lookup=cursor.getString(0);
                        }
                        if (lookup==null || !lookup.equals(row.getString("lookup"))) throw new IllegalArgumentException("Contact changed; reload contacts");
                        try (InputStream input=getContext().getContentResolver().openInputStream(Uri.withAppendedPath(ContactsContract.Contacts.CONTENT_VCARD_URI,Uri.encode(lookup)))) {
                            byte[] buffer=new byte[16384]; int size;
                            while ((size=input.read(buffer))!=-1) output.write(buffer,0,size);
                        }
                        output.write(new byte[]{13,10});
                    }
                } catch (Exception error) {
                    try { pipe[1].closeWithError(error.getMessage()); } catch (Exception ignored) {}
                }
            },"TwistContactExport").start();
            return pipe[0];
        } catch (Exception error) { throw new java.io.FileNotFoundException(error.getMessage()); }
    }
    public boolean onCreate() { return true; }
    void checkCaller() {
        int uid = Binder.getCallingUid();
        if (uid != 2000 && uid != android.os.Process.myUid()) throw new SecurityException("USB debugging shell access only");
    }
    void require(String permission) {
        if (getContext().checkSelfPermission(permission) != PackageManager.PERMISSION_GRANTED)
            throw new SecurityException("Open Twist Contacts Bridge on your phone and allow Contacts access");
    }
    MatrixCursor payload(byte[] value) {
        MatrixCursor result = new MatrixCursor(new String[]{"payload"});
        result.addRow(new Object[]{Base64.encodeToString(value, Base64.NO_WRAP)});
        return result;
    }
    public Cursor query(Uri uri, String[] projection, String selection, String[] args, String order) {
        checkCaller();
        long identity = Binder.clearCallingIdentity();
        try {
            require(Manifest.permission.READ_CONTACTS);
            if ("vcard".equals(uri.getPathSegments().get(0))) {
                long id = Long.parseLong(uri.getLastPathSegment());
                String lookup = null;
                try (Cursor cursor = getContext().getContentResolver().query(ContentUris.withAppendedId(ContactsContract.Contacts.CONTENT_URI,id), new String[]{ContactsContract.Contacts.LOOKUP_KEY},null,null,null)) {
                    if (cursor != null && cursor.moveToFirst()) lookup = cursor.getString(0);
                }
                if (lookup == null) throw new IllegalArgumentException("Contact no longer exists");
                if (!lookup.equals(uri.getQueryParameter("lookup"))) throw new IllegalArgumentException("Contact changed; reload contacts");
                ByteArrayOutputStream bytes = new ByteArrayOutputStream();
                try (InputStream input = getContext().getContentResolver().openInputStream(Uri.withAppendedPath(ContactsContract.Contacts.CONTENT_VCARD_URI,Uri.encode(lookup)))) {
                    byte[] buffer = new byte[8192]; int size;
                    while ((size=input.read(buffer)) != -1) {
                        if (bytes.size()+size > 16*1024*1024) throw new IllegalArgumentException("Contact too large");
                        bytes.write(buffer,0,size);
                    }
                }
                return payload(bytes.toByteArray());
            }
            int offset = Math.max(0,Integer.parseInt(uri.getQueryParameter("offset") == null ? "0" : uri.getQueryParameter("offset")));
            int limit = 200;
            JSONArray result = new JSONArray();
            String[] columns = {ContactsContract.Contacts._ID,ContactsContract.Contacts.DISPLAY_NAME_PRIMARY,ContactsContract.Contacts.LOOKUP_KEY};
            try (Cursor contacts = getContext().getContentResolver().query(ContactsContract.Contacts.CONTENT_URI, columns,null,null,ContactsContract.Contacts._ID+" ASC")) {
                int index = 0;
                while (contacts != null && contacts.moveToNext()) {
                    if (index++ < offset) continue;
                    if (result.length() >= limit) break;
                    long id = contacts.getLong(0);
                    JSONArray phones = new JSONArray();
                    try (Cursor numbers = getContext().getContentResolver().query(ContactsContract.CommonDataKinds.Phone.CONTENT_URI,new String[]{ContactsContract.CommonDataKinds.Phone.NUMBER},ContactsContract.CommonDataKinds.Phone.CONTACT_ID+"=?",new String[]{Long.toString(id)},null)) {
                        while (numbers != null && numbers.moveToNext()) phones.put(numbers.getString(0));
                    }
                    JSONObject row = new JSONObject();
                    row.put("contact_id",Long.toString(id)); row.put("name",contacts.getString(1));
                    row.put("lookup",contacts.getString(2)); row.put("numbers",phones); result.put(row);
                }
            }
            return payload(result.toString().getBytes("UTF-8"));
        } catch (SecurityException e) { throw e; }
        catch (Exception e) { throw new IllegalArgumentException(e.getMessage(),e); }
        finally { Binder.restoreCallingIdentity(identity); }
    }
    public int delete(Uri uri, String selection, String[] args) {
        checkCaller();
        long identity = Binder.clearCallingIdentity();
        try {
            require(Manifest.permission.WRITE_CONTACTS); require(Manifest.permission.READ_CONTACTS);
            if (uri.getPathSegments().size()!=2 || !"contacts".equals(uri.getPathSegments().get(0))) throw new IllegalArgumentException("Select one contact ID");
            long id = Long.parseLong(uri.getLastPathSegment());
            Uri contact = ContentUris.withAppendedId(ContactsContract.Contacts.CONTENT_URI,id);
            try (Cursor cursor = getContext().getContentResolver().query(contact,new String[]{ContactsContract.Contacts.LOOKUP_KEY},null,null,null)) {
                if (cursor == null || !cursor.moveToFirst()) return 0;
                if (!cursor.getString(0).equals(uri.getQueryParameter("lookup"))) throw new IllegalArgumentException("Contact changed; reload contacts");
            }
            return getContext().getContentResolver().delete(contact,null,null);
        } finally { Binder.restoreCallingIdentity(identity); }
    }
    public String getType(Uri uri) { return "application/json"; }
    public Uri insert(Uri uri, ContentValues values) { throw new UnsupportedOperationException(); }
    public int update(Uri uri, ContentValues values, String selection, String[] args) { throw new UnsupportedOperationException(); }
}
