$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path $PSScriptRoot -Parent)
$javaTools = (Get-ChildItem tools/java -Directory | Select-Object -First 1).FullName + '/bin'
$androidJar = (Resolve-Path tools/sdk/platform/android-35/android.jar).Path
$androidBuildTools = (Resolve-Path tools/sdk/build-tools/android-15).Path
New-Item -ItemType Directory -Path companion/build/classes,companion/build/dex,companion/signing -Force | Out-Null
python -c "from pathlib import Path; import secrets; p=Path('companion/signing/password.txt'); p.write_text(secrets.token_hex(24)) if not p.exists() else None"
$javaSources = Get-ChildItem companion/src -Recurse -Filter '*.java' | Select-Object -ExpandProperty FullName
$qrJar = (Resolve-Path companion/lib/zxing-core-3.5.3.jar).Path
& "$javaTools/javac.exe" --release 8 -classpath "$androidJar;$qrJar" -d companion/build/classes $javaSources
if ($LASTEXITCODE -ne 0) { throw 'Java compile failed' }
& "$javaTools/jar.exe" --create --file companion/build/classes.jar -C companion/build/classes .
& "$javaTools/java.exe" -cp "$androidBuildTools/lib/d8.jar" com.android.tools.r8.D8 --lib $androidJar --min-api 23 --output companion/build/dex companion/build/classes.jar $qrJar
if ($LASTEXITCODE -ne 0) { throw 'DEX build failed' }
& "$androidBuildTools/aapt2.exe" link --manifest companion/AndroidManifest.xml -I $androidJar -o companion/build/base.apk
if ($LASTEXITCODE -ne 0) { throw 'Resource build failed' }
python -c "import zipfile; z=zipfile.ZipFile('companion/build/base.apk','a'); z.write('companion/build/dex/classes.dex','classes.dex'); z.close()"
python -c "import zipfile; z=zipfile.ZipFile('companion/build/base.apk','a'); z.write('companion/lib/ZXING-LICENSE.txt','assets/ZXING-LICENSE.txt'); z.close()"
if (-not (Test-Path companion/signing/contacts.p12)) {
    & "$javaTools/keytool.exe" -genkeypair -keystore companion/signing/contacts.p12 -storepass:file companion/signing/password.txt -keypass:file companion/signing/password.txt -alias contacts -dname 'CN=Twist MediaBridge' -keyalg RSA -keysize 3072 -validity 3650
}
& "$javaTools/java.exe" -jar "$androidBuildTools/lib/apksigner.jar" sign --ks companion/signing/contacts.p12 --ks-key-alias contacts --ks-pass file:companion/signing/password.txt --out companion/TwistContactsBridge.apk companion/build/base.apk
if ($LASTEXITCODE -ne 0) { throw 'Signing failed' }
& "$javaTools/java.exe" -jar "$androidBuildTools/lib/apksigner.jar" verify companion/TwistContactsBridge.apk
if ($LASTEXITCODE -ne 0) { throw 'Signature validation failed' }
Copy-Item companion/TwistContactsBridge.apk companion/TwistCompanion.apk -Force
