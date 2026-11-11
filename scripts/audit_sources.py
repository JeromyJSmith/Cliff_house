"""Read-only capture inventory. Writes a new named persistent evidence directory.
No imports, conversions, registrations, training, database writes or source changes.
"""
import argparse,collections,datetime,hashlib,json,math,mmap,pathlib,struct,subprocess

def audit(root,out):
    root=root.resolve();out=out.resolve();out.mkdir(parents=True,exist_ok=False)
    rows=[];clouds=[];media=[]
    for p in sorted(root.rglob('*')):
        if '.git' in p.parts or p.is_symlink() or not p.is_file() or out in p.parents:continue
        s=p.stat();rows.append({'path':str(p.relative_to(root)),'bytes':s.st_size,'mtime_ns':s.st_mtime_ns})
    for p in sorted(root.glob('*.ply')):
        with p.open('rb') as f:
            header=bytearray()
            for _ in range(1000):
                line=f.readline();header.extend(line)
                if line.strip()==b'end_header':break
            else:raise ValueError(f'No header end: {p}')
            text=header.decode('ascii');lines=text.splitlines()
            props=[x for x in lines if x.startswith('property ')]
            expected=['property float x','property float y','property float z','property uchar red','property uchar green','property uchar blue']
            if 'format binary_little_endian 1.0' not in text or props!=expected:raise ValueError(f'Unsupported root cloud schema: {p}')
            n=int(next(x for x in lines if x.startswith('element vertex ')).split()[-1]);payload=p.stat().st_size-len(header)
            if payload!=n*15:raise ValueError(f'Payload/count mismatch: {p}')
            ids=range(0,n,max(1,n//20000));mins=[math.inf]*3;maxs=[-math.inf]*3;finite=0;samples=0
            with mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ) as mm:
                for i in ids:
                    xyz=struct.unpack_from('<fff',mm,len(header)+15*i);samples+=1
                    if all(math.isfinite(v) for v in xyz):
                        finite+=1;mins=[min(a,b) for a,b in zip(mins,xyz)];maxs=[max(a,b) for a,b in zip(maxs,xyz)]
            clouds.append({'path':str(p),'vertex_count':n,'bytes':p.stat().st_size,'header_sha256':hashlib.sha256(header).hexdigest(),'header':text,'stride_bytes':15,'payload_size_matches_header':True,'sampled_points':samples,'sampled_finite_points':finite,'sampled_bounds_min':mins,'sampled_bounds_max':maxs,'coordinate_units':'unverified','registration_to_other_sources':'unverified','bounds_are_full_extents':False})
    for p in sorted(root.rglob('*')):
        if p.suffix.lower() not in {'.insv','.mp4'} or '.git' in p.parts:continue
        cmd=['ffprobe','-v','error','-show_entries','format=duration:stream=index,codec_type,codec_name,width,height,r_frame_rate','-of','json',str(p)]
        r=subprocess.run(cmd,capture_output=True,text=True)
        media.append({'path':str(p),'returncode':r.returncode,'metadata':json.loads(r.stdout) if r.returncode==0 else None,'error':r.stderr[:2000] if r.returncode else None})
    obj=root/'processed/model.obj';geom={'path':str(obj),'present':obj.exists()}
    if obj.exists():
        counts=collections.Counter()
        with obj.open(errors='replace') as f:
            for line in f:
                if line.startswith(('v ','vt ','vn ','f ')):counts[line.split(' ',1)[0]]+=1
        geom['counts']=dict(counts);geom['coordinate_units']='unverified';geom['registration']='unverified'
    result={'recorded_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_root':str(root),'purpose':'present-day Cliff House reconnaissance','inventory':rows,'clouds':clouds,'media':media,'processed_obj':geom,'raw_files_fully_hashed':False,'note':'stat inventory and SHA-256 of PLY headers only; sample bounds are not full extents or dimensional qualification. No source was edited.'}
    (out/'source-audit.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'inventory_files':len(rows),'site_scape_points':sum(x['vertex_count'] for x in clouds),'clouds':len(clouds),'media':len(media),'obj':geom,'evidence':str(out/'source-audit.json')},indent=2))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source-root',required=True,type=pathlib.Path);p.add_argument('--output',required=True,type=pathlib.Path);a=p.parse_args();audit(a.source_root,a.output)
