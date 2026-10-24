"""Offline asset/PE icon verification and native-size inspection sheet."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
from PIL import Image,ImageDraw

ROOT=Path(__file__).resolve().parents[1]
SIZES=(16,32,48,128,256)


def ico_entries(path):
    raw=Path(path).read_bytes()
    reserved,kind,count=struct.unpack_from('<HHH',raw)
    if reserved or kind!=1: raise ValueError('Not an ICO')
    result=[]
    for index in range(count):
        width,height,_,_,_,_,size,offset=struct.unpack_from('<BBBBHHII',raw,6+index*16)
        payload=raw[offset:offset+size]
        if len(payload)!=size: raise ValueError('Truncated icon entry')
        result.append({'size':(width or 256,height or 256),'sha256':hashlib.sha256(payload).hexdigest()})
    return result


def check_exe_icon(exe,ico):
    import pefile
    pe=pefile.PE(str(exe))
    try:
        resources={}
        for group in pe.DIRECTORY_ENTRY_RESOURCE.entries:
            if group.id!=3: continue
            for name in group.directory.entries:
                for language in name.directory.entries:
                    record=language.data.struct
                    resources[name.id]=pe.get_data(record.OffsetToData,record.Size)
        groups=[]
        for group in pe.DIRECTORY_ENTRY_RESOURCE.entries:
            if group.id!=14: continue
            for name in group.directory.entries:
                for language in name.directory.entries:
                    record=language.data.struct; raw=pe.get_data(record.OffsetToData,record.Size)
                    _,kind,count=struct.unpack_from('<HHH',raw)
                    entries=[]
                    for index in range(count):
                        width,height,_,_,_,_,size,identifier=struct.unpack_from('<BBBBHHIH',raw,6+index*14)
                        payload=resources[identifier]
                        if len(payload)!=size: raise ValueError('PE icon size mismatch')
                        entries.append({'size':(width or 256,height or 256),'sha256':hashlib.sha256(payload).hexdigest()})
                    groups.append(entries)
        expected=ico_entries(ico)
        return any(sorted(g,key=lambda e:e['size'])==sorted(expected,key=lambda e:e['size']) for g in groups)
    finally: pe.close()


def inspection_sheet(ico,output):
    sheet=Image.new('RGB',(760,390),'#ececea'); draw=ImageDraw.Draw(sheet)
    with Image.open(ico) as source:
        x=20
        for size in SIZES:
            draw.text((x,15),f'{size} x {size}',fill='#222222')
            frame=source.ico.getimage((size,size)).convert('RGBA')
            sheet.paste(frame,(x,45),frame)
            x+=size+26
    sheet.save(output)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe',type=Path)
    parser.add_argument('--sheet',type=Path)
    args=parser.parse_args()
    ico=ROOT/'assets/branding/quartz-q.ico'
    entries=ico_entries(ico)
    result={'entries':entries,'required_sizes_present':set((s,s) for s in SIZES).issubset(e['size'] for e in entries)}
    if args.exe: result['exe_icon_matches_supplied_ico']=check_exe_icon(args.exe,ico)
    if args.sheet: inspection_sheet(ico,args.sheet)
    print(json.dumps(result,indent=2))
    return 0 if result['required_sizes_present'] and result.get('exe_icon_matches_supplied_ico',True) else 1


if __name__=='__main__': raise SystemExit(main())
