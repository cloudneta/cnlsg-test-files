#!/usr/bin/env python3
"""CNLSG Case 6; run as root on the named EC2 host."""
import base64, copy, datetime, hashlib, json, os, pathlib, subprocess, sys, time, urllib.request, urllib.error, urllib.parse
HERE=pathlib.Path(__file__).resolve().parent
STAMP=datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
BACK=pathlib.Path('/opt/cnlsg-case6/backups')/STAMP

def run(*args, input=None):
    return subprocess.check_output(args,input=input,text=True).strip()
def inspect(name): return json.loads(run('docker','inspect',name))[0]
def save(path,data):
    path=pathlib.Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+'.case6-tmp'); tmp.write_text(data); os.replace(tmp,path)
def backup(path):
    p=pathlib.Path(path); BACK.mkdir(parents=True,exist_ok=True); os.chmod(BACK,0o700)
    if p.exists(): (BACK/p.name).write_bytes(p.read_bytes())
def wait(url):
    for _ in range(60):
        try:
            with urllib.request.urlopen(url,timeout=3) as r:
                if r.status==200:return
        except Exception: pass
        time.sleep(2)
    raise RuntimeError('Readiness timeout: '+url)
def api(method,path,data=None):
    headers={'Content-Type':'application/json'}
    if os.getenv('GRAFANA_TOKEN'): headers['Authorization']='Bearer '+os.environ['GRAFANA_TOKEN']
    else:
        creds=os.getenv('GRAFANA_USER','admin')+':'+os.environ['GRAFANA_PASSWORD']
        headers['Authorization']='Basic '+base64.b64encode(creds.encode()).decode()
    req=urllib.request.Request(os.getenv('GRAFANA_URL','http://127.0.0.1:3000')+path,headers=headers,method=method,data=None if data is None else json.dumps(data).encode())
    with urllib.request.urlopen(req,timeout=60) as r:return json.load(r)
def get(path):
    try:return api('GET',path)
    except urllib.error.HTTPError as e:
        if e.code==404:return None
        raise

def tempo():
    assert run('hostname')=='INTERNAL-REPOSITORY','Run on INTERNAL-REPOSITORY'
    run('docker','network','inspect','monitoring-network')
    image='grafana/tempo:3.0.0'
    try:run('docker','image','inspect',image)
    except subprocess.CalledProcessError:
        tar=os.getenv('TEMPO_TAR','/opt/downloads/tempo.tar')
        if not pathlib.Path(tar).is_file():raise RuntimeError('Import linux/amd64 Tempo 3.0.0 tar first; set TEMPO_TAR. No internet pull is attempted.')
        run('docker','load','-i',tar)
    info=json.loads(run('docker','image','inspect',image))[0]
    assert info['Architecture']=='amd64','Tempo image must be amd64'
    cfg='''server:
  http_listen_port: 3200
distributor:
  receivers:
    otlp:
      protocols:
        grpc:
          endpoint: 0.0.0.0:4317
        http:
          endpoint: 0.0.0.0:4318
storage:
  trace:
    backend: local
    wal:
      path: /var/tempo/wal
    local:
      path: /var/tempo/blocks
'''
    path=pathlib.Path('/opt/tempo/tempo.yaml')
    exists=run('docker','ps','-a','--filter','name=^/tempo$','--format','{{.Names}}')=='tempo'
    if exists:
        c=inspect('tempo')
        assert path.exists() and path.read_text()==cfg,'Existing Tempo config differs; review manually'
        assert c['Config']['Image']==image and c['HostConfig']['NetworkMode']=='monitoring-network','Existing Tempo differs'
        assert any(m['Source']==str(path) and m['Destination']=='/etc/tempo.yaml' for m in c['Mounts'])
        assert any(m['Source']=='/opt/tempo/data' and m['Destination']=='/var/tempo' for m in c['Mounts'])
        for port in ('4317','4318'):
            assert c['HostConfig']['PortBindings'].get(port+'/tcp')==[{'HostIp':'10.10.1.103','HostPort':port}],'Tempo ports differ'
        run('docker','start','tempo')
    else:
        if path.exists() and path.read_text()!=cfg:raise RuntimeError('Existing unmanaged Tempo configuration; review manually')
        save(path,cfg); pathlib.Path('/opt/tempo/data').mkdir(exist_ok=True)
        run('chown','-R','10001:10001','/opt/tempo/data')
        run('docker','run','-d','--pull=never','--name','tempo','--restart','unless-stopped','--network','monitoring-network','-p','10.10.1.103:4317:4317','-p','10.10.1.103:4318:4318','-v',str(path)+':/etc/tempo.yaml:ro','-v','/opt/tempo/data:/var/tempo',image,'-config.file=/etc/tempo.yaml')
    # Query through Grafana's shared network; no host port 3200 required.
    ds={'name':'CNLSG Tempo','uid':'cnlsg-tempo','type':'tempo','access':'proxy','url':'http://tempo:3200','jsonData':{'httpMethod':'GET'}}
    current=get('/api/datasources/uid/cnlsg-tempo')
    if current:
        assert current['type']=='tempo' and current['url']==ds['url'],'Datasource UID collision'
    else:api('POST','/api/datasources',ds)
    for _ in range(60):
        try:
            health=api('GET','/api/datasources/uid/cnlsg-tempo/health')
            if health.get('status')=='OK':break
        except Exception:pass
        time.sleep(2)
    else:raise RuntimeError('Tempo datasource readiness failed')
    print('Tempo and Grafana datasource ready')

def tracing():
    assert run('hostname')=='INTERNAL-LITELLM','Run on INTERNAL-LITELLM'
    c=inspect('litellm'); cfgpath=pathlib.Path('/opt/litellm/config.yaml'); alloy=pathlib.Path('/etc/alloy/config.alloy')
    # Guard exact baseline so custom container options are never silently discarded.
    assert c['Config']['Image']=='ghcr.io/berriai/litellm:v1.98.0'
    assert c['HostConfig']['NetworkMode']=='litellm-network'
    assert c['Config']['Cmd']==['--config','/app/config.yaml','--port','4000']
    assert len(c['Mounts'])==1 and c['Mounts'][0]['Source']==str(cfgpath) and c['Mounts'][0]['Destination']=='/app/config.yaml'
    assert c['HostConfig']['PortBindings']=={'4000/tcp':[{'HostIp':'','HostPort':'4000'}]},'Container ports changed'
    assert not c['HostConfig']['Privileged'] and not c['HostConfig']['CapAdd'] and not c['HostConfig']['Devices']
    assert not c['HostConfig']['Memory'] and not c['HostConfig']['NanoCpus'],'Custom resource limits; review manually'
    gateway=json.loads(run('docker','network','inspect','litellm-network'))[0]['IPAM']['Config'][0]['Gateway']
    env={'OTEL_EXPORTER':'otlp_http','OTEL_ENDPOINT':'http://'+gateway+':4318/v1/traces','OTEL_SERVICE_NAME':'litellm','LITELLM_OTEL_V2':'true'}
    # Use the installed LiteLLM Python/PyYAML; keep comments and original YAML text.
    code='''import sys,yaml
from yaml.nodes import MappingNode,SequenceNode
text=sys.stdin.read(); old=yaml.safe_load(text); root=yaml.compose(text)
def mapping(node):
 if not isinstance(node,MappingNode): raise ValueError('Expected mapping')
 keys=[k.value for k,v in node.value]
 if len(keys)!=len(set(keys)): raise ValueError('Duplicate YAML keys')
 return {k.value:v for k,v in node.value}
entries=mapping(root); edits=[]
if 'litellm_settings' not in entries:
 text+='\\nlitellm_settings:\\n  success_callback: ["otel"]\\n  failure_callback: ["otel"]\\n'
else:
 node=entries['litellm_settings']; settings=mapping(node)
 for key in ('success_callback','failure_callback'):
  if key in settings:
   n=settings[key]
   if not isinstance(n,SequenceNode): raise ValueError('Callback must be YAML list')
   val=yaml.safe_load(text[n.start_mark.index:n.end_mark.index])
   if 'otel' not in val:
    replacement=yaml.safe_dump(val+['otel'],default_flow_style=True).strip()
    if not n.flow_style: replacement+='\\n'+' '*n.end_mark.column
    edits.append((n.start_mark.index,n.end_mark.index,replacement))
  else: edits.append((node.end_mark.index,node.end_mark.index,'  '+key+': ["otel"]\\n'))
 for a,b,s in sorted(edits,reverse=True): text=text[:a]+s+text[b:]
new=yaml.safe_load(text)
for key,value in old.items():
 if key!='litellm_settings': assert new[key]==value
for key,value in old.get('litellm_settings',{}).items():
 if key not in ('success_callback','failure_callback'): assert new['litellm_settings'][key]==value
assert new['general_settings']['store_prompts_in_spend_logs'] is True
assert new['general_settings']['disable_spend_logs'] is False
for key in ('success_callback','failure_callback'): assert 'otel' in new['litellm_settings'][key]
print(text,end='')
'''
    original=cfgpath.read_text(); updated=run('docker','exec','-i','litellm','python','-c',code,input=original)+'\n'
    oldalloy=alloy.read_text(); begin='// BEGIN CNLSG CASE6 TRACE'; end='// END CNLSG CASE6 TRACE'
    import re
    base=re.sub(re.escape(begin)+r'.*?'+re.escape(end)+'\\n?', '', oldalloy,flags=re.S)
    if 'otelcol.receiver.otlp "litellm_trace"' in base or 'otelcol.exporter.otlp "tempo"' in base:raise RuntimeError('Unmanaged OTLP blocks already exist; review manually')
    block=f'''{begin}
otelcol.receiver.otlp "litellm_trace" {{
  http {{
    endpoint = "{gateway}:4318"
  }}
  output {{
    traces = [otelcol.exporter.otlp.tempo.input]
  }}
}}
otelcol.exporter.otlp "tempo" {{
  client {{
    endpoint = "10.10.1.103:4317"
    tls {{
      insecure = true
    }}
  }}
}}
{end}
'''
    candidate=base.rstrip()+'\n\n'+block
    tmp=alloy.with_name('case6-candidate.alloy'); tmp.write_text(candidate)
    run('alloy','validate',str(tmp)); tmp.unlink()
    existing=dict(x.split('=',1) for x in c['Config']['Env'])
    if updated==original and candidate==oldalloy and all(existing.get(k)==v for k,v in env.items()):
        run('systemctl','is-active','alloy'); wait('http://127.0.0.1:4000/health/liveliness'); print('Tracing already configured'); return
    backup(cfgpath); backup(alloy)
    (BACK/'litellm-inspect.json').write_text(json.dumps(c,indent=2))
    oldname='litellm-before-case6-'+STAMP; replaced=False
    try:
        # Write in place: Docker single-file bind mounts must keep their inode.
        cfgpath.write_text(updated); alloy.write_text(candidate)
        run('systemctl','restart','alloy'); run('systemctl','is-active','alloy')
        run('docker','stop','litellm'); run('docker','rename','litellm',oldname); replaced=True
        args=['docker','run','-d','--pull=never','--name','litellm','--restart',c['HostConfig']['RestartPolicy']['Name'],'--network','litellm-network','-p','4000:4000','-v',str(cfgpath)+':/app/config.yaml']
        existing.update(env)
        for k,v in existing.items():args+=['-e',k+'='+v]
        args += [c['Image']]+c['Config']['Cmd']
        run(*args); wait('http://127.0.0.1:4000/health/liveliness')
    except Exception:
        cfgpath.write_text(original); alloy.write_text(oldalloy)
        subprocess.run(['systemctl','restart','alloy'],check=False)
        if replaced:
            subprocess.run(['docker','rm','-f','litellm'],check=False)
            run('docker','rename',oldname,'litellm'); run('docker','start','litellm')
        raise
    print('Tracing enabled. Rollback container: '+oldname+'; backups: '+str(BACK))

def link(query,kind):
    # Restore Grafana variables AFTER URL encoding, preserving variable recognition.
    panes={'trace':{'datasource':'cnlsg-tempo','queries':[{'refId':'A','queryType':kind,'query':query}],'range':{'from':'${__from}','to':'${__to}'}}}
    encoded=urllib.parse.quote(json.dumps(panes,separators=(',',':')),safe='')
    import re
    for var in re.findall(r'\$\{[^}]+\}',json.dumps(panes)):encoded=encoded.replace(urllib.parse.quote(var,safe=''),var)
    return '/explore?schemaVersion=1&panes='+encoded

def dashboard():
    assert run('hostname')=='INTERNAL-REPOSITORY'
    assert get('/api/datasources/uid/cnlsg-tempo'),'Run step 01 first'
    uid='cnlsg-postgres'
    ds={'uid':uid,'name':'CNLSG Audit PostgreSQL','type':'grafana-postgresql-datasource','access':'proxy','url':'10.10.1.101:5432','user':'litellm','jsonData':{'database':'litellm','sslmode':'disable','postgresVersion':1600,'timescaledb':False},'secureJsonData':{'password':os.getenv('AUDIT_DB_PASSWORD','litellm-password')}}
    current=get('/api/datasources/uid/'+uid)
    if current:
        assert current['type']==ds['type'] and current['url']==ds['url'] and current['user']=='litellm' and current['jsonData'].get('database')=='litellm','Datasource collision'
    else:api('POST','/api/datasources',ds)
    panels=[]
    for n,title,filename,y,h in [(1,'Request Audit','request-audit.sql',0,14),(2,'Tool Audit','tool-audit.sql',14,10)]:
        source={'type':ds['type'],'uid':uid}
        panels.append({'id':n,'title':title,'type':'table','gridPos':{'x':0,'y':y,'w':24,'h':h},'datasource':source,'targets':[{'refId':'A','datasource':source,'format':'table','rawQuery':True,'editorMode':'code','rawSql':(HERE/filename).read_text()}],'options':{'showHeader':True,'cellHeight':'sm'},'fieldConfig':{'defaults':{},'overrides':[{'matcher':{'id':'byName','options':'request_id'},'properties':[{'id':'links','value':[{'title':'Find request in Tempo','url':link('{ span.gen_ai.response.id = "${__value.raw}" }','traceql')}]}]}]}})
    source={'type':'tempo','uid':'cnlsg-tempo'}
    panels.append({'id':3,'title':'Trace Overview','type':'table','gridPos':{'x':0,'y':24,'w':24,'h':10},'datasource':source,'targets':[{'refId':'A','datasource':source,'queryType':'traceql','query':'{ rootName = "POST /v1/messages" }','limit':100}],'transformations':[{'id':'organize','options':{'excludeByName':{'nested':True},'indexByName':{'startTime':0,'traceID':1,'traceService':2,'traceName':3,'traceDuration':4},'renameByName':{'startTime':'Time','traceID':'Trace ID','traceService':'Service','traceName':'Operation','traceDuration':'Duration'}}}],'fieldConfig':{'defaults':{},'overrides':[{'matcher':{'id':'byName','options':'Trace ID'},'properties':[{'id':'links','value':[{'title':'View Trace in Tempo','url':link('${__value.raw}','traceId')}]}]},{'matcher':{'id':'byName','options':'Duration'},'properties':[{'id':'unit','value':'ms'}]}]},'options':{'showHeader':True,'cellHeight':'sm'}})
    # Validate queries before writing dashboard; empty datasets are valid.
    for panel in panels:
        result=api('POST','/api/ds/query',{'from':'now-24h','to':'now','queries':panel['targets']})
        for value in result.get('results',{}).values():
            if value.get('error') or value.get('status',200)>=400:raise RuntimeError(panel['title']+': '+str(value))
        assert result.get('results'),'No query results returned'
    uid='airgap-llm-audit-trace'; old=get('/api/dashboards/uid/'+uid)
    d=copy.deepcopy(old['dashboard']) if old else {'uid':uid,'title':'Air-Gap LLM Audit & Trace','tags':['CNLSG','Air-Gap'],'timezone':'browser','schemaVersion':41,'version':0,'time':{'from':'now-24h','to':'now'},'refresh':'30s','panels':[]}
    if old and old.get('meta',{}).get('provisioned'):raise RuntimeError('Dashboard is provisioned; review its provider')
    others=[p for p in d['panels'] if p['title'] not in ['Request Audit','Tool Audit','Trace Overview']]
    assert not any(p['id'] in (1,2,3) for p in others),'Panel ID collision'
    if d['panels']==panels+others:print('Dashboard already configured');return
    if old:
        BACK.mkdir(parents=True,exist_ok=True); os.chmod(BACK,0o700)
        (BACK/'dashboard.json').write_text(json.dumps(old,indent=2))
    d['panels']=panels+others
    result=api('POST','/api/dashboards/db',{'dashboard':d,'folderUid':old['meta'].get('folderUid','') if old else '', 'overwrite':True,'message':'CNLSG Case 6 Audit and Trace'})
    print(json.dumps(result,indent=2))

if __name__=='__main__':
    if os.geteuid()!=0:raise SystemExit('Run with sudo/root')
    if sys.argv[1] in ('tempo','dashboard') and not (os.getenv('GRAFANA_TOKEN') or os.getenv('GRAFANA_PASSWORD')):raise SystemExit('Set GRAFANA_PASSWORD or GRAFANA_TOKEN')
    try:
        {'tempo':tempo,'tracing':tracing,'dashboard':dashboard}[sys.argv[1]]()
    except subprocess.CalledProcessError:
        raise SystemExit('A system command failed. Review service/container state and backups; command arguments are omitted to protect credentials.')
    except Exception as error:
        raise SystemExit(str(error) or type(error).__name__)
