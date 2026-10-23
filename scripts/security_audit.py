"""Redacted working-tree and reachable-history inventory; never print matches."""
import json, re, subprocess
from pathlib import Path
PATTERNS = {'telegram_token': r'\b\d{7,12}:[A-Za-z0-9_-]{30,}\b', 'github_token': r'\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})', 'email': r'\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b', 'possible_nik': r'(?<!\d)\d{16}(?!\d)', 'private_key': r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'}
def classify(data):
 return {name: len(re.findall(pattern, data)) for name, pattern in PATTERNS.items() if re.search(pattern,data)}
def main():
 paths=subprocess.check_output(['git','ls-files','-z']).decode().split('\0')
 report=[]
 for name in filter(None,paths):
  p=Path(name)
  if p.is_file():
   findings=classify(p.read_bytes().decode('utf-8',errors='ignore'))
   sensitive=bool(re.search(r'(^user_data/|cookies/|riwayat/|\.env$|durations\.json$|/(?:akun|nik)\.txt$|__pycache__)',name))
   if findings or sensitive: report.append({'path':name,'categories':findings,'sensitive_path':sensitive})
 history=[]
 for sha in subprocess.check_output(['git','rev-list','--all']).decode().splitlines():
  files=subprocess.check_output(['git','ls-tree','-rz','--name-only',sha]).decode().split('\0')
  count={}
  for path in filter(None,files):
   data=subprocess.check_output(['git','show',f'{sha}:{path}'])
   for k,v in classify(data.decode('utf-8',errors='ignore')).items(): count[k]=count.get(k,0)+v
  history.append({'commit':sha,'counts':count})
 print(json.dumps({'tracked_findings':report,'reachable_history':history},indent=2))
if __name__=='__main__': main()
