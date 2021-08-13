
.\adb.exe shell rm -rf /data/dji_scratch/sdk
.\adb.exe push dji_scratch/sdk /data/dji_scratch/.

.\adb.exe push dji_scratch/bin/dji_scratch.py /data/dji_scratch/bin/.

.\adb.exe push dji.json /data/.

.\adb.exe push dji_hdvt_uav /data/.

.\adb.exe push patch.sh /data/.

