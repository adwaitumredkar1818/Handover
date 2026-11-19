import subprocess
import sys
import uuid

v = f"v_cross_{uuid.uuid4().hex[:8]}"
cmd = [sys.executable, "backend/tests/run_cross_proc_worker.py", v]

env = dict(PYTHONPATH="backend;.")
p1 = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
p2 = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

out1, err1 = p1.communicate()
out2, err2 = p2.communicate()

print("Process 1 Output:", out1.strip())
print("Process 2 Output:", out2.strip())
