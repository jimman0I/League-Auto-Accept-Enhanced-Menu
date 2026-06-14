#!/usr/bin/env python3
"""Hextech Auto-Accept v2 — Recommended Runes, Tag Filters, Phase Display"""

import json, os, sys, time, threading, subprocess, re
import requests, urllib3
from requests.auth import HTTPBasicAuth
urllib3.disable_warnings()
IS_WINDOWS = sys.platform == "win32"

# ═══════════════════════════════════════════════════════════════
#  VERSION & AUTO-UPDATE
# ═══════════════════════════════════════════════════════════════
APP_VERSION = "1.0.0"
GITHUB_REPO = "jimman0I/League-Auto-Accept-Enhanced-Menu"  # owner/repo used for auto-update checks

def check_for_update(log=None):
    """Check GitHub releases for a newer version."""
    def _log(m):
        if log:log(m)
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
        r = requests.get(url, timeout=8, headers={'Accept':'application/vnd.github.v3+json','User-Agent':'HextechDraft'})
        if r.status_code == 200:
            data = r.json()
            latest = data.get('tag_name','').lstrip('v')
            if latest and latest != APP_VERSION:
                # Find the .exe asset
                exe_url = None
                for asset in data.get('assets',[]):
                    if asset['name'].lower().endswith('.exe'):
                        exe_url = asset.get('browser_download_url')
                        break
                return {"available":True,"current":APP_VERSION,"latest":latest,
                        "url":exe_url,"notes":data.get('body','')[:200],"html_url":data.get('html_url','')}
            return {"available":False,"current":APP_VERSION,"latest":latest}
        elif r.status_code == 404:
            _log("[DEBUG] Update: repo not found — set GITHUB_REPO in the script")
        return {"available":False,"current":APP_VERSION,"latest":APP_VERSION}
    except Exception as e:
        _log(f"[DEBUG] Update check failed: {e}")
        return {"available":False,"current":APP_VERSION,"latest":APP_VERSION}

def download_update(exe_url, log=None):
    """Download new EXE and prepare for restart."""
    def _log(m):
        if log:log(m)
    if not exe_url:
        _log("[DEBUG] No download URL");return False
    try:
        _log("[DEBUG] Downloading update...")
        r = requests.get(exe_url, timeout=120, stream=True,
                        headers={'User-Agent':'HextechDraft','Accept':'application/octet-stream'})
        if r.status_code != 200:
            _log(f"[DEBUG] Download failed: {r.status_code}");return False
        # Save next to current exe
        if getattr(sys,'frozen',False):
            current = sys.executable
            new_path = current + ".update"
        else:
            current = os.path.abspath(__file__)
            new_path = current + ".update.exe"
        total = int(r.headers.get('content-length',0))
        downloaded = 0
        with open(new_path,'wb') as f:
            for chunk in r.iter_content(chunk_size=65536):
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = int(downloaded*100/total)
                    if pct % 20 == 0:_log(f"[DEBUG] Downloading... {pct}%")
        _log(f"[SUCCESS] Downloaded update to {os.path.basename(new_path)}")
        # Create a batch script to replace the exe and restart
        if IS_WINDOWS and getattr(sys,'frozen',False):
            bat = os.path.join(os.path.dirname(current),"_update.bat")
            with open(bat,'w') as f:
                f.write(f'@echo off\ntimeout /t 2 /nobreak >nul\n')
                f.write(f'del "{current}"\n')
                f.write(f'move "{new_path}" "{current}"\n')
                f.write(f'start "" "{current}"\n')
                f.write(f'del "%~f0"\n')
            _log("[SUCCESS] Update ready — restart the app to apply")
            return bat
        return new_path
    except Exception as e:
        _log(f"[DEBUG] Download error: {e}");return False

# ═══════════════════════════════════════════════════════════════
#  LCU CONNECTION
# ═══════════════════════════════════════════════════════════════
def find_lcu():
    if not IS_WINDOWS: return None,None,"Not Windows"
    for fn,nm in [(_ps,"PowerShell"),(_lf,"Lockfile"),(_wm,"WMIC"),(_pu,"psutil")]:
        p,t,m=fn()
        if p: return p,t,nm
    return None,None,"Not found"
def _ps():
    try:
        r=subprocess.run(["powershell","-NoProfile","-Command",
            "Get-CimInstance Win32_Process -Filter \"name='LeagueClientUx.exe'\" | Select-Object -ExpandProperty CommandLine"],
            capture_output=True,text=True,timeout=8,creationflags=0x08000000)
        return _pc(r.stdout)
    except: return None,None,"err"
def _lf():
    try:
        r=subprocess.run(["powershell","-NoProfile","-Command",
            "Get-CimInstance Win32_Process -Filter \"name='LeagueClientUx.exe'\" | Select-Object -ExpandProperty ExecutablePath"],
            capture_output=True,text=True,timeout=8,creationflags=0x08000000)
        exe=r.stdout.strip()
        if exe:
            lf=os.path.join(os.path.dirname(exe),"lockfile")
            if os.path.exists(lf):
                p=open(lf).read().strip().split(':')
                if len(p)>=5: return p[2],p[3],"ok"
    except: pass
    for d in ["C:","D:","E:"]:
        lf=f"{d}\\Riot Games\\League of Legends\\lockfile"
        try:
            if os.path.exists(lf):
                p=open(lf).read().strip().split(':')
                if len(p)>=5: return p[2],p[3],"ok"
        except: pass
    return None,None,"nf"
def _wm():
    try:
        r=subprocess.run(["wmic","PROCESS","WHERE","name='LeagueClientUx.exe'","GET","commandline"],
            capture_output=True,text=True,timeout=8,creationflags=0x08000000)
        return _pc(r.stdout)
    except: return None,None,"err"
def _pu():
    try:
        import psutil
        for p in psutil.process_iter(['name','cmdline']):
            try:
                if p.info['name'] and 'LeagueClientUx' in p.info['name']:
                    port=tok=None
                    for a in (p.info.get('cmdline') or []):
                        if '--app-port=' in str(a): port=str(a).split('=')[1]
                        elif '--remoting-auth-token=' in str(a): tok=str(a).split('=')[1]
                    if port and tok: return port,tok,"ok"
            except: continue
    except ImportError: pass
    return None,None,"nf"
def _pc(t):
    if not t or 'LeagueClientUx' not in t: return None,None,"nf"
    pm=re.search(r'--app-port=(\d+)',t);tm=re.search(r'--remoting-auth-token=([\w_-]+)',t)
    if pm and tm: return pm.group(1),tm.group(1),"ok"
    return None,None,"pf"
def mk_session(port,tok):
    s=requests.Session();s.verify=False;s.auth=HTTPBasicAuth('riot',tok)
    s._base=f"https://127.0.0.1:{port}";return s
def api_get(s,p):
    try:
        r=s.get(f"{s._base}{p}",timeout=2)
        if r.status_code==200: return r.json()
    except: pass
    return None
def api_patch(s,p,d):
    try: return s.patch(f"{s._base}{p}",json=d,timeout=3).status_code
    except: return 0
def api_post(s,p,d=None):
    try: return s.post(f"{s._base}{p}",json=d or{},timeout=2).status_code
    except: return 0
def api_put(s,p,d):
    try: return s.put(f"{s._base}{p}",json=d,timeout=2).status_code
    except: return 0

# ═══════════════════════════════════════════════════════════════
#  DATA
# ═══════════════════════════════════════════════════════════════
DDRAGON_VER = "14.10.1"
def fetch_champions():
    global DDRAGON_VER
    try:
        DDRAGON_VER=requests.get("https://ddragon.leagueoflegends.com/api/versions.json",timeout=5).json()[0]
        data=requests.get(f"https://ddragon.leagueoflegends.com/cdn/{DDRAGON_VER}/data/en_US/champion.json",timeout=5).json()['data']
        return sorted([{"id":int(v['key']),"name":v['name'],"img":k,"tags":v.get('tags',[])} for k,v in data.items()],key=lambda x:x['name'])
    except: return []
def fetch_spells():
    return [{"id":21,"name":"Barrier","img":"SummonerBarrier"},{"id":1,"name":"Cleanse","img":"SummonerBoost"},
            {"id":13,"name":"Clarity","img":"SummonerMana"},{"id":3,"name":"Exhaust","img":"SummonerExhaust"},
            {"id":4,"name":"Flash","img":"SummonerFlash"},{"id":6,"name":"Ghost","img":"SummonerHaste"},
            {"id":7,"name":"Heal","img":"SummonerHeal"},{"id":14,"name":"Ignite","img":"SummonerDot"},
            {"id":32,"name":"Mark","img":"SummonerSnowball"},{"id":11,"name":"Smite","img":"SummonerSmite"},
            {"id":12,"name":"Teleport","img":"SummonerTeleport"}]

def fetch_rune_pages(session):
    pages=api_get(session,"/lol-perks/v1/pages")
    return [p for p in (pages or []) if p.get('isDeletable',False)]

def fetch_runes_reforged():
    """Fetch all rune trees with images from Data Dragon."""
    try:
        data=requests.get(f"https://ddragon.leagueoflegends.com/cdn/{DDRAGON_VER}/data/en_US/runesReforged.json",timeout=5).json()
        perk_map={}  # perkId -> {name, icon_url}
        style_map={}  # styleId -> {name, icon_url}
        for tree in data:
            style_map[tree['id']]={'name':tree['name'],'icon':'https://ddragon.leagueoflegends.com/cdn/img/'+tree['icon']}
            for slot in tree.get('slots',[]):
                for rune in slot.get('runes',[]):
                    perk_map[rune['id']]={'name':rune['name'],'icon':'https://ddragon.leagueoflegends.com/cdn/img/'+rune['icon'],'key':rune.get('key','')}
        return {'perks':perk_map,'styles':style_map}
    except:
        return {'perks':{},'styles':{}}


# ═══════════════════════════════════════════════════════════════
#  BUILD SOURCES — U.GG / Blitz / Lolalytics / ddragon
# ═══════════════════════════════════════════════════════════════

VALID_ITEMS=set()
def load_valid_items():
    global VALID_ITEMS
    try:
        data=requests.get(f"https://ddragon.leagueoflegends.com/cdn/{DDRAGON_VER}/data/en_US/item.json",timeout=8).json()
        VALID_ITEMS=set(int(k) for k in data.get('data',{}).keys())
    except:pass

def _champ_url_name(champ_key):
    """Convert ddragon key to URL name for build sites."""
    if not champ_key:return None
    specials={"MonkeyKing":"wukong","Nunu":"nunu","FiddleSticks":"fiddlesticks","AurelionSol":"aurelion-sol","BelVeth":"belveth","ChoGath":"cho-gath","DrMundo":"dr-mundo","JarvanIV":"jarvan-iv","KaiSa":"kaisa","KhaZix":"kha-zix","KogMaw":"kog-maw","LeBlanc":"leblanc","LeeSin":"lee-sin","MasterYi":"master-yi","MissFortune":"miss-fortune","RekSai":"rek-sai","RenataGlascc":"renata-glasc","TahmKench":"tahm-kench","TwistedFate":"twisted-fate","VelKoz":"vel-koz","XinZhao":"xin-zhao"}
    if champ_key in specials:return specials[champ_key]
    return champ_key.lower()

def fetch_ugg_build(champ_key, position, log=None):
    """Fetch runes + items + spells from U.GG — proven JSON data."""
    def _log(m):
        if log:log(m)
    name=_champ_url_name(champ_key)
    if not name:return None,None,None
    pos_map={'TOP':'top','JUNGLE':'jungle','MIDDLE':'mid','BOTTOM':'adc','UTILITY':'support'}
    pos=pos_map.get(position,'top')
    url=f"https://u.gg/lol/champions/{name}/build/{pos}"
    _log(f"[DEBUG] U.GG: {name}/{pos}")
    try:
        resp=requests.get(url,timeout=12,headers={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36','Accept':'text/html,application/xhtml+xml','Accept-Language':'en-US,en;q=0.9'})
        if resp.status_code!=200:_log(f"[DEBUG] U.GG: HTTP {resp.status_code}");return None,None,None
        html=resp.text
        # Extract rec_runes (pick the one with most matches = most reliable)
        rune_blocks=re.findall(r'"stat_shards":\{[^}]+\}[^}]*"rec_runes":\{([^}]+)\}',html)
        shard_blocks=re.findall(r'"stat_shards":\{"matches":\d+,"wins":\d+,"win_rate":[\d.]+,"active_shards":\[([^\]]+)\]',html)
        if not rune_blocks:
            rune_blocks=re.findall(r'"rec_runes":\{([^}]+)\}',html)
        # Parse all rune blocks and pick best
        best_rune=None;best_matches=0
        for rb in rune_blocks:
            m_matches=re.search(r'"matches":(\d+)',rb)
            m_primary=re.search(r'"primary_style":(\d+)',rb)
            m_sub=re.search(r'"sub_style":(\d+)',rb)
            m_perks=re.search(r'"active_perks":\[([^\]]+)\]',rb)
            if m_matches and m_primary and m_perks:
                matches=int(m_matches.group(1))
                if matches>best_matches:
                    best_matches=matches
                    wr_m=re.search(r'"win_rate":([\d.]+)',rb)
                    wr=float(wr_m.group(1)) if wr_m else 0
                    perks=[int(x) for x in m_perks.group(1).split(',')]
                    psty=int(m_primary.group(1))
                    ssty=int(m_sub.group(1)) if m_sub else 8100
                    best_rune={"name":f"U.GG · {wr:.1f}% WR","primaryStyleId":psty,"subStyleId":ssty,
                        "selectedPerkIds":perks,"source":"recommended"}
        # Add shards to best rune
        if best_rune and shard_blocks:
            shards=[int(x) for x in shard_blocks[0].split(',')]
            best_rune['selectedPerkIds']+=shards
        runes=[best_rune] if best_rune else None
        if runes:_log(f"[SUCCESS] U.GG runes: {len(best_rune['selectedPerkIds'])} perks ({best_matches} matches)")
        # Extract items
        items=None
        boot_ids={3006,3009,3010,3020,3047,3111,3117,3158}
        starters=re.findall(r'"rec_starting_items":\{"matches":(\d+),[^}]*"ids":\[([^\]]+)\]',html)
        cores=re.findall(r'"rec_core_items":\{"matches":(\d+),[^}]*"ids":\[([^\]]+)\]',html)
        if cores:
            # Pick best by match count
            best_s=max(starters,key=lambda x:int(x[0])) if starters else None
            best_c=max(cores,key=lambda x:int(x[0]))
            items={'starter':[],'core':[],'boots':[],'situational':[]}
            if best_s:items['starter']=[int(x) for x in best_s[1].split(',')][:3]
            core_ids=[int(x) for x in best_c[1].split(',')]
            for iid in core_ids:
                if iid in boot_ids:items['boots'].append(iid)
                else:items['core'].append(iid)
            # Get situational from item_options
            opts=re.findall(r'"item_options_1":\[([^\]]+)\]',html)
            if opts:
                for m2 in re.finditer(r'"id":(\d+)',opts[0]):
                    iid=int(m2.group(1))
                    if iid not in items['core'] and iid not in items['boots'] and len(items['situational'])<4:
                        items['situational'].append(iid)
            _log(f"[SUCCESS] U.GG items: {len(items['starter'])}s {len(items['core'])}c {len(items['boots'])}b {len(items['situational'])}x")
        # Extract spells
        spells=None
        spell_blocks=re.findall(r'"rec_summoner_spells":\{"matches":(\d+),[^}]*"ids":\[([^\]]+)\]',html)
        if spell_blocks:
            best_sp=max(spell_blocks,key=lambda x:int(x[0]))
            spells=[int(x) for x in best_sp[1].split(',')][:2]
            _log(f"[SUCCESS] U.GG spells: {spells}")
        return runes,items,spells
    except Exception as e:
        _log(f"[DEBUG] U.GG error: {e}");return None,None,None

def fetch_blitz_build(champ_key, position, log=None):
    """Fetch items from Blitz.gg — good item data."""
    def _log(m):
        if log:log(m)
    name=_champ_url_name(champ_key)
    if not name:return None,None,None
    pos_map={'TOP':'top','JUNGLE':'jungle','MIDDLE':'mid','BOTTOM':'adc','UTILITY':'support'}
    pos=pos_map.get(position,'top')
    url=f"https://blitz.gg/lol/champions/{name}/build/{pos}"
    _log(f"[DEBUG] Blitz: {name}/{pos}")
    try:
        resp=requests.get(url,timeout=12,headers={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36','Accept':'text/html'})
        if resp.status_code!=200:_log(f"[DEBUG] Blitz: HTTP {resp.status_code}");return None,None,None
        html=resp.text
        boot_ids={3006,3009,3010,3020,3047,3111,3117,3158}
        items={'starter':[],'core':[],'boots':[],'situational':[]}
        # Starter items: "startingItems":[{"itemIds":["1055","2003"],...}]
        starters=re.findall(r'"startingItems":\[.*?"itemIds":\[([^\]]+)\].*?"games":(\d+)',html)
        if starters:
            best=max(starters,key=lambda x:int(x[1]))
            items['starter']=[int(x.strip().strip('"').strip("'")) for x in best[0].split(',')][:3]
        # Core items: "coreItems":[{"itemIds":"3047,3161,6699",...}]
        cores=re.findall(r'"coreItems":\[.*?"itemIds":"([^"]+)".*?"games":(\d+)',html)
        if cores:
            best=max(cores,key=lambda x:int(x[1]))
            for iid in [int(x) for x in best[0].split(',')]:
                if iid in boot_ids:items['boots'].append(iid)
                elif len(items['core'])<6:items['core'].append(iid)
        total=sum(len(v) for v in items.values())
        if total>=2:
            _log(f"[SUCCESS] Blitz items: {len(items['starter'])}s {len(items['core'])}c {len(items['boots'])}b")
            return None,items,None
        return None,None,None
    except Exception as e:
        _log(f"[DEBUG] Blitz error: {e}");return None,None,None

def fetch_lolalytics_build(champ_key, position, log=None):
    """Fetch from Lolalytics."""
    def _log(m):
        if log:log(m)
    name=_champ_url_name(champ_key)
    if not name:return None,None,None
    pos_map={'TOP':'top','JUNGLE':'jungle','MIDDLE':'middle','BOTTOM':'bottom','UTILITY':'support'}
    pos=pos_map.get(position,'top')
    url=f"https://lolalytics.com/lol/{name}/build/?lane={pos}"
    _log(f"[DEBUG] Lolalytics: {name}/{pos}")
    try:
        resp=requests.get(url,timeout=12,headers={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36','Accept':'text/html'})
        if resp.status_code!=200:_log(f"[DEBUG] Lolalytics: HTTP {resp.status_code}");return None,None,None
        # Lolalytics has data in script tags — look for perk and item patterns
        html=resp.text
        # Look for rune data
        rune_matches=re.findall(r'"primary_style":(\d+).*?"sub_style":(\d+).*?"active_perks":\[([^\]]+)\]',html)
        if rune_matches:
            psty,ssty,perks_str=rune_matches[0]
            perks=[int(x) for x in perks_str.split(',')]
            runes=[{"name":"Lolalytics Rec","primaryStyleId":int(psty),"subStyleId":int(ssty),"selectedPerkIds":perks,"source":"recommended"}]
            return runes,None,None
        return None,None,None
    except Exception as e:
        _log(f"[DEBUG] Lolalytics error: {e}");return None,None,None

def fetch_ddragon_items(champ_key, log=None):
    """Fetch Riot's default recommended items from ddragon."""
    def _log(m):
        if log:log(m)
    if not champ_key:return None
    url=f"https://ddragon.leagueoflegends.com/cdn/{DDRAGON_VER}/data/en_US/champion/{champ_key}.json"
    try:
        resp=requests.get(url,timeout=8)
        if resp.status_code!=200:return None
        d=resp.json().get('data',{}).get(champ_key,{})
        recs=d.get('recommended',[])
        if not recs:return None
        best=recs[0]
        for r in recs:
            if 'CLASSIC' in r.get('mode','').upper():best=r;break
        items={'starter':[],'core':[],'boots':[],'situational':[]}
        boot_ids={3006,3009,3010,3020,3047,3111,3117,3158}
        for block in best.get('blocks',[]):
            btype=block.get('type','').lower()
            bids=[int(bi.get('id',0)) for bi in block.get('items',[]) if bi.get('id')]
            if 'start' in btype:items['starter']=bids[:3]
            elif 'essential' in btype or 'core' in btype or 'offensive' in btype:
                for iid in bids:
                    if iid in boot_ids and len(items['boots'])<2:items['boots'].append(iid)
                    elif len(items['core'])<6:items['core'].append(iid)
            elif 'defensive' in btype or 'situational' in btype:items['situational']=bids[:4]
            else:
                for iid in bids:
                    if iid in boot_ids and len(items['boots'])<2:items['boots'].append(iid)
                    elif len(items['core'])<6:items['core'].append(iid)
                    elif len(items['situational'])<4:items['situational'].append(iid)
        if sum(len(v) for v in items.values())>=2:
            _log(f"[SUCCESS] ddragon items: {sum(len(v) for v in items.values())} total")
            return items
        return None
    except:return None

DEFAULT_RUNES={
    'Fighter':{"name":"Conqueror","primaryStyleId":8000,"subStyleId":8400,
        "selectedPerkIds":[8010,9111,9104,8299,8444,8451,5005,5008,5001],"source":"default"},
    'Tank':{"name":"Grasp","primaryStyleId":8400,"subStyleId":8300,
        "selectedPerkIds":[8437,8401,8429,8451,8345,8347,5005,5002,5001],"source":"default"},
    'Mage':{"name":"Arcane Comet","primaryStyleId":8200,"subStyleId":8300,
        "selectedPerkIds":[8229,8226,8210,8237,8345,8347,5007,5008,5001],"source":"default"},
    'Assassin':{"name":"Electrocute","primaryStyleId":8100,"subStyleId":8200,
        "selectedPerkIds":[8112,8143,8138,8135,8210,8236,5008,5008,5001],"source":"default"},
    'Marksman':{"name":"Lethal Tempo","primaryStyleId":8000,"subStyleId":8100,
        "selectedPerkIds":[8008,9111,9104,8014,8139,8135,5005,5008,5001],"source":"default"},
    'Support':{"name":"Summon Aery","primaryStyleId":8200,"subStyleId":8400,
        "selectedPerkIds":[8214,8226,8210,8237,8444,8453,5008,5008,5001],"source":"default"},
}
def get_default_runes(champ_tags):
    if not champ_tags:return dict(DEFAULT_RUNES['Fighter'])
    for tag in champ_tags:
        if tag in DEFAULT_RUNES:return dict(DEFAULT_RUNES[tag])
    return dict(DEFAULT_RUNES['Fighter'])

# Source order by user preference
SOURCES={'ugg':fetch_ugg_build,'blitz':fetch_blitz_build,'lolalytics':fetch_lolalytics_build}

def fetch_recommended_runes(session, champ_id, position, champ_key=None, champ_tags=None, log=None, source_pref=None):
    """Fetch runes: always U.GG → LCU → defaults."""
    def _log(m):
        if log:log(m)
    results=[]
    # Always try U.GG first for runes (most reliable)
    if champ_key:
        try:
            runes,_,_=fetch_ugg_build(champ_key,position,log=log)
            if runes:
                results=runes
                _log(f"[SUCCESS] Runes from U.GG")
        except:pass
    # LCU fallback
    if not results and session:
        pos_l=(position or 'top').lower()
        for ep in [f"/lol-perks/v1/recommended-pages/champion/{champ_id}/position/{pos_l}",
                    f"/lol-perks/v1/recommended-pages/champion/{champ_id}"]:
            if results:break
            try:
                data=api_get(session,ep)
                if data and isinstance(data,list):
                    for page in data:
                        pids=page.get('selectedPerkIds') or page.get('perks',[])
                        psty=page.get('primaryStyleId')
                        if pids and len(pids)>=4 and psty:
                            results.append({"name":"LCU Recommended","primaryStyleId":int(psty),
                                "subStyleId":int(page.get('subStyleId',0) or 0),
                                "selectedPerkIds":[int(p) for p in pids],"source":"recommended"})
            except:pass
    if not results:
        _log(f"[DEBUG] Using class defaults")
        results=[get_default_runes(champ_tags)]
    return results[:3]

def fetch_recommended_items(session, champ_id, position, champ_key=None, log=None, source_pref=None):
    """Fetch items: preferred source → other sources → ddragon."""
    def _log(m):
        if log:log(m)
    order=[]
    if source_pref and source_pref in SOURCES:
        order=[source_pref]+[s for s in SOURCES if s!=source_pref]
    else:
        order=list(SOURCES.keys())
    for src_name in order:
        fetcher=SOURCES[src_name]
        if champ_key:
            try:
                _,items,_=fetcher(champ_key,position,log=log)
                if items and sum(len(v) for v in items.values())>=2:
                    _log(f"[SUCCESS] Items from {src_name.upper()}")
                    return items
                elif src_name==source_pref:
                    _log(f"[DEBUG] {src_name.upper()} had no items, trying next...")
            except:pass
    # ddragon fallback
    if champ_key:
        items=fetch_ddragon_items(champ_key,log=log)
        if items:return items
    return None
    # ddragon fallback
    if champ_key:
        items=fetch_ddragon_items(champ_key,log=log)
        if items:return items
    return None

def fetch_recommended_spells(session, champ_id, position, champ_key=None, log=None, source_pref=None):
    """Fetch summoner spells from preferred source."""
    if not champ_key:return None
    order=[]
    if source_pref and source_pref in SOURCES:
        order=[source_pref]+[s for s in SOURCES if s!=source_pref]
    else:
        order=list(SOURCES.keys())
    for src_name in order:
        fetcher=SOURCES[src_name]
        try:
            _,_,spells=fetcher(champ_key,position,log=log)
            if spells and len(spells)>=2:return spells
        except:pass
    return None

def write_item_set(session, summoner_id, champ_id, champ_name, items_data, log=None):
    """Write an item set to the LCU client."""
    def _log(m):
        if log:log(m)
    if not items_data:return False
    try:
        blocks=[]
        if items_data.get('starter'):
            blocks.append({"type":"Starter","items":[{"id":str(i),"count":1} for i in items_data['starter']]})
        if items_data.get('core'):
            blocks.append({"type":"Core Build","items":[{"id":str(i),"count":1} for i in items_data['core']]})
        if items_data.get('boots'):
            blocks.append({"type":"Boots","items":[{"id":str(i),"count":1} for i in items_data['boots']]})
        if items_data.get('situational'):
            blocks.append({"type":"Situational","items":[{"id":str(i),"count":1} for i in items_data['situational']]})
        if not blocks:_log("[DEBUG] Items: no blocks to write");return False
        
        item_set={
            "title":f"Hextech · {champ_name}"[:30],
            "type":"custom",
            "map":"any",
            "mode":"any",
            "priority":False,
            "sortrank":0,
            "associatedChampions":[int(champ_id)],
            "associatedMaps":[],
            "blocks":blocks
        }
        # Try to get the correct summoner ID
        sid=summoner_id
        try:
            s_data=api_get(session,"/lol-summoner/v1/current-summoner")
            if s_data:sid=s_data.get('summonerId') or s_data.get('accountId') or summoner_id
        except:pass
        
        _log(f"[DEBUG] Writing item set for {champ_name} (sid={sid})")
        
        # Method 1: Get existing sets and append
        existing=api_get(session,f"/lol-item-sets/v1/item-sets/{sid}/sets")
        if existing and isinstance(existing,dict) and 'itemSets' in existing:
            sets=existing['itemSets']
            sets=[s for s in sets if not (s.get('title','').startswith('Hextech') and int(champ_id) in s.get('associatedChampions',[]))]
            sets.append(item_set)
            body={"itemSets":sets,"timestamp":str(int(time.time()*1000)),"accountId":existing.get('accountId',sid)}
            r=session.put(f"{session._base}/lol-item-sets/v1/item-sets/{sid}/sets",json=body,timeout=5)
            if r.status_code in (200,201,204):
                _log(f"[SUCCESS] Item set imported for {champ_name}")
                return True
            _log(f"[DEBUG] Item set PUT failed: {r.status_code}: {r.text[:80]}")
        
        # Method 2: Try POST directly
        r2=session.post(f"{session._base}/lol-item-sets/v1/item-sets/{sid}/sets",json={"itemSets":[item_set]},timeout=5)
        if r2.status_code in (200,201,204):
            _log(f"[SUCCESS] Item set imported via POST for {champ_name}")
            return True
        _log(f"[DEBUG] Item set POST failed: {r2.status_code}")
        return False
    except Exception as e:
        _log(f"[DEBUG] Item set error: {e}")
        return False

def fetch_champion_mastery(session, summoner_id, champ_id):
    """Fetch mastery level and points for a champion."""
    try:
        data=api_get(session,f"/lol-collections/v1/inventories/{summoner_id}/champion-mastery")
        if data:
            for m in data:
                if m.get('championId')==champ_id:
                    return {"level":m.get('championLevel',0),"points":m.get('championPoints',0),
                            "chest":m.get('chestGranted',False)}
    except:pass
    return None

def _perk_tree(perk_id):
    pid=int(perk_id)
    if pid in PERK_MAP: return PERK_MAP[pid][0]
    return None

def _is_stat_shard(pid):
    return int(pid) in VALID_SHARDS

# Perk map built dynamically from ddragon — always matches current patch
PERK_MAP={}
VALID_SHARDS={5001,5002,5003,5005,5007,5008}
TREE_DEFAULTS={}

def build_perk_map():
    """Build PERK_MAP from Data Dragon runesReforged.json — always up to date."""
    global PERK_MAP,TREE_DEFAULTS,DDRAGON_VER
    # Refresh ddragon version
    try:
        v=requests.get("https://ddragon.leagueoflegends.com/api/versions.json",timeout=5).json()
        if v:DDRAGON_VER=v[0]
    except:pass
    try:
        data=requests.get(f"https://ddragon.leagueoflegends.com/cdn/{DDRAGON_VER}/data/en_US/runesReforged.json",timeout=8).json()
        for tree in data:
            tree_id=tree['id']
            defaults=[]
            for slot_idx,slot in enumerate(tree.get('slots',[])):
                for rune in slot.get('runes',[]):
                    PERK_MAP[rune['id']]=(tree_id,slot_idx)
                    if not defaults or len(defaults)<=slot_idx:
                        defaults.append(rune['id'])
            TREE_DEFAULTS[tree_id]=defaults
        # Pad defaults to 4 rows
        for tid in TREE_DEFAULTS:
            while len(TREE_DEFAULTS[tid])<4:
                TREE_DEFAULTS[tid].append(TREE_DEFAULTS[tid][-1])
    except:
        # Fallback hardcoded if ddragon fails
        PERK_MAP.update({
            8005:(8000,0),8008:(8000,0),8021:(8000,0),8010:(8000,0),
            9101:(8000,1),9111:(8000,1),8009:(8000,1),
            9104:(8000,2),9105:(8000,2),9103:(8000,2),
            8014:(8000,3),8017:(8000,3),8299:(8000,3),
            8112:(8100,0),8124:(8100,0),8128:(8100,0),9923:(8100,0),
            8126:(8100,1),8139:(8100,1),8143:(8100,1),
            8136:(8100,2),8120:(8100,2),8138:(8100,2),
            8135:(8100,3),8134:(8100,3),8105:(8100,3),8106:(8100,3),
            8214:(8200,0),8229:(8200,0),8230:(8200,0),
            8224:(8200,1),8226:(8200,1),8275:(8200,1),
            8210:(8200,2),8234:(8200,2),8233:(8200,2),
            8237:(8200,3),8232:(8200,3),8236:(8200,3),
            8351:(8300,0),8360:(8300,0),8369:(8300,0),
            8306:(8300,1),8304:(8300,1),8313:(8300,1),
            8321:(8300,2),8316:(8300,2),8345:(8300,2),
            8347:(8300,3),8410:(8300,3),8352:(8300,3),
            8437:(8400,0),8439:(8400,0),8465:(8400,0),
            8446:(8400,1),8463:(8400,1),8401:(8400,1),
            8429:(8400,2),8444:(8400,2),8473:(8400,2),
            8451:(8400,3),8453:(8400,3),8242:(8400,3),
        })
        TREE_DEFAULTS.update({
            8000:[8005,9111,9104,8299],8100:[8112,8139,8138,8135],
            8200:[8229,8226,8210,8237],8300:[8351,8306,8345,8347],
            8400:[8437,8401,8429,8451],
        })

def build_perk_map_from_lcu(session):
    """Build PERK_MAP from the actual LCU client — always matches current patch."""
    global PERK_MAP,TREE_DEFAULTS
    try:
        styles=api_get(session,"/lol-perks/v1/styles")
        if styles and isinstance(styles,list):
            PERK_MAP.clear();TREE_DEFAULTS.clear()
            for style in styles:
                tree_id=style['id']
                defaults=[]
                for slot_idx,slot in enumerate(style.get('slots',[])):
                    for perk in slot.get('perks',[]):
                        # perk is just an ID integer in LCU
                        if isinstance(perk,int):
                            PERK_MAP[perk]=(tree_id,slot_idx)
                            if len(defaults)<=slot_idx:defaults.append(perk)
                        elif isinstance(perk,dict):
                            pid=perk.get('id')
                            if pid:
                                PERK_MAP[pid]=(tree_id,slot_idx)
                                if len(defaults)<=slot_idx:defaults.append(pid)
                while len(defaults)<4:defaults.append(defaults[-1] if defaults else 0)
                TREE_DEFAULTS[tree_id]=defaults
            return True
    except:pass
    # Also try /lol-perks/v1/perks for individual perk details
    try:
        perks=api_get(session,"/lol-perks/v1/perks")
        if perks and isinstance(perks,list):
            for p in perks:
                pid=p.get('id');tree=p.get('styleId');row=p.get('slotType','')
                if pid and tree:
                    # Convert slotType to row index
                    row_map={'kKeyStone':0,'kMixedRegularSplashable':1,'kStatMod':-1}
                    ridx=row_map.get(row,-1)
                    if ridx<0:
                        # Try to infer from name patterns
                        ridx=p.get('row',1)
                    if pid not in PERK_MAP:
                        PERK_MAP[pid]=(tree,ridx)
            return True
    except:pass
    return False

def validate_perks_against_lcu(session, perk_ids):
    """Check each perk ID against LCU and return which are valid."""
    try:
        perks=api_get(session,"/lol-perks/v1/perks")
        if perks and isinstance(perks,list):
            valid_ids=set(p.get('id') for p in perks if p.get('id'))
            valid_ids.update(VALID_SHARDS)
            return [pid for pid in perk_ids if pid in valid_ids]
    except:pass
    return perk_ids  # Can't validate, return as-is

# Initialize perk map and valid items after all functions are defined
build_perk_map()
load_valid_items()

def _fix_rune_data(rune_data, log=None, champ_name=None):
    """Build a valid 9-perk array: 1 keystone + 3 primary minor + 2 secondary + 3 shards."""
    def _log(m):
        if log:log(m)
    page_name=f"Hextech ({champ_name})" if champ_name else rune_data.get('name','Hextech')
    pids=[int(p) for p in rune_data.get('selectedPerkIds',[])]
    psty=int(rune_data.get('primaryStyleId',0))
    ssty=int(rune_data.get('subStyleId',0) or 0)
    if not pids or not psty:return None

    def guess_tree_row(pid):
        """If perk not in PERK_MAP, try to guess tree from ID range."""
        if pid in PERK_MAP:return PERK_MAP[pid]
        # Guess by range: 8000-8099=Precision, 8100-8199=Domination, etc
        if 8000<=pid<8100:return (8000, -1)
        if 8100<=pid<8200:return (8100, -1)
        if 8200<=pid<8300:return (8200, -1)
        if 8300<=pid<8400:return (8300, -1)
        if 8400<=pid<8500:return (8400, -1)
        if 9100<=pid<9200:return (8000, -1)  # Legend perks
        if 9900<=pid<9999:return (8100, -1)  # HoB etc
        return None

    # Bucket perks
    primary_by_row={};secondary_by_row={};shards=[];candidates=[]
    for pid in pids:
        if pid in VALID_SHARDS:
            shards.append(pid);continue
        info=guess_tree_row(pid)
        if not info:
            _log(f"[DEBUG] Skipping unknown ID: {pid}");continue
        tree,row=info
        if tree==psty:
            if row>=0:
                if row not in primary_by_row:primary_by_row[row]=pid
            else:
                candidates.append(('primary',pid,tree))
        elif ssty and tree==ssty:
            if row>=0:
                if row not in secondary_by_row:secondary_by_row[row]=pid
            else:
                candidates.append(('secondary',pid,tree))
        else:
            candidates.append(('unknown',pid,tree))

    # Place unplaced primary candidates into empty rows
    for role,pid,tree in candidates:
        if role=='primary' and tree==psty:
            for r in [0,1,2,3]:
                if r not in primary_by_row:primary_by_row[r]=pid;break

    # Auto-detect secondary tree from unknown candidates
    if len(secondary_by_row)<2:
        trees={}
        for role,pid,tree in candidates:
            if tree!=psty:trees.setdefault(tree,[]).append(pid)
        if trees:
            best=max(trees,key=lambda t:len(trees[t]))
            if not ssty:ssty=best
            target_tree=ssty
            for pid in trees.get(target_tree,[]):
                info=guess_tree_row(pid)
                if info:
                    _,row=info
                    if row>=0:
                        if row not in secondary_by_row and row>0:secondary_by_row[row]=pid
                    else:
                        for r in [1,2,3]:
                            if r not in secondary_by_row:secondary_by_row[r]=pid;break

    # Build primary array
    primary_final=[]
    if 0 in primary_by_row:primary_final.append(primary_by_row[0])
    elif psty in TREE_DEFAULTS:primary_final.append(TREE_DEFAULTS[psty][0])
    else:_log("[DEBUG] No keystone found");return None
    for r in [1,2,3]:
        if r in primary_by_row:primary_final.append(primary_by_row[r])
        elif psty in TREE_DEFAULTS and r<len(TREE_DEFAULTS[psty]):primary_final.append(TREE_DEFAULTS[psty][r])

    # Build secondary array
    secondary_final=[]
    sec_rows=sorted([r for r in secondary_by_row if r>0])
    for r in sec_rows[:2]:secondary_final.append(secondary_by_row[r])
    if len(secondary_final)<2:
        if not ssty:
            for t in [8100,8200,8300,8400,8000]:
                if t!=psty:ssty=t;break
        if ssty in TREE_DEFAULTS:
            for r in range(1,min(4,len(TREE_DEFAULTS[ssty]))):
                if len(secondary_final)>=2:break
                dp=TREE_DEFAULTS[ssty][r]
                if dp not in secondary_final:secondary_final.append(dp)

    # Shards
    SHARD_ROWS=[{5008,5005,5007},{5008,5002,5003},{5001,5002,5003}]
    SHARD_DEFAULTS=[5008,5008,5001]
    valid_shards=[]
    used=list(shards)
    for ri in range(3):
        placed=False
        for i,s in enumerate(used):
            if s in SHARD_ROWS[ri]:valid_shards.append(s);used.pop(i);placed=True;break
        if not placed:valid_shards.append(SHARD_DEFAULTS[ri])

    final=primary_final[:4]+secondary_final[:2]+valid_shards[:3]
    if len(final)!=9:
        _log(f"[DEBUG] Wrong length {len(final)}: P={primary_final} S={secondary_final} Sh={valid_shards}")
        return None
    _log(f"[DEBUG] Runes: KS={final[0]} P={final[1:4]} S={final[4:6]} Sh={final[6:9]}")
    return {"name":page_name[:25],"primaryStyleId":psty,
            "subStyleId":ssty or 8100,"selectedPerkIds":final,"current":True}

def write_runes_to_page(session, page_id, rune_data, log=None, champ_name=None):
    """Write runes by validating data, then delete+recreate page."""
    def _log(m):
        if log:log(m)
    try:
        # Rebuild perk map from LCU if possible (ensures current patch)
        build_perk_map_from_lcu(session)
        body=_fix_rune_data(rune_data,log=log,champ_name=champ_name)
        if not body:
            _log("[DEBUG] Rune data invalid — could not build valid 9-perk array")
            return False
        # Validate all perk IDs against the actual client
        validated=validate_perks_against_lcu(session,body['selectedPerkIds'])
        if len(validated)!=9:
            _log(f"[DEBUG] Some perks invalid after LCU validation: had {body['selectedPerkIds']}, valid={validated}")
            # Replace invalid ones with defaults
            body2=_fix_rune_data({"name":body['name'],"primaryStyleId":body['primaryStyleId'],
                "subStyleId":body['subStyleId'],"selectedPerkIds":validated},log=log,champ_name=champ_name)
            if body2:body=body2
        perks=body['selectedPerkIds']
        _log(f"[DEBUG] Runes: P={body['primaryStyleId']} S={body['subStyleId']}")
        _log(f"[DEBUG] KS={perks[0]} Minor={perks[1:4]} Sec={perks[4:6]} Sh={perks[6:9]}")
        
        # DELETE old page + POST new one
        try:session.delete(f"{session._base}/lol-perks/v1/pages/{page_id}",timeout=3)
        except:pass
        r=session.post(f"{session._base}/lol-perks/v1/pages",json=body,timeout=3)
        if r.status_code in (200,201,204):
            _log(f"[SUCCESS] Runes imported!")
            return True
        _log(f"[DEBUG] POST failed ({r.status_code}): {r.text[:100]}")
        
        # Fallback: PUT
        r2=session.put(f"{session._base}/lol-perks/v1/pages/{page_id}",json=body,timeout=3)
        if r2.status_code in (200,204):
            _log(f"[SUCCESS] Runes imported via PUT!")
            return True
        _log(f"[DEBUG] PUT failed ({r2.status_code}): {r2.text[:100]}")
        return False
    except Exception as e:
        _log(f"[DEBUG] Rune write error: {e}")
        return False

# ═══════════════════════════════════════════════════════════════
#  ANTI-AFK
# ═══════════════════════════════════════════════════════════════
if IS_WINDOWS:
    import ctypes;u32=ctypes.windll.user32;k32=ctypes.windll.kernel32
    def find_game_hwnd():
        for cls in ["RiotWindowClass","RCLIENT"]:
            h=u32.FindWindowW(cls,None)
            if h: return h
        import ctypes.wintypes;result=[0]
        def cb(hwnd,_):
            l=u32.GetWindowTextLengthW(hwnd)
            if l>0:
                buf=ctypes.create_unicode_buffer(l+1);u32.GetWindowTextW(hwnd,buf,l+1)
                if 'League of Legends' in buf.value and 'Client' not in buf.value:
                    result[0]=hwnd;return False
            return True
        u32.EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_bool,ctypes.wintypes.HWND,ctypes.wintypes.LPARAM)(cb),0)
        return result[0]
    def game_focused():h=find_game_hwnd();return h!=0 and u32.GetForegroundWindow()==h
    def idle_secs():
        class L(ctypes.Structure):_fields_=[('s',ctypes.c_uint),('t',ctypes.c_uint)]
        i=L();i.s=ctypes.sizeof(L);u32.GetLastInputInfo(ctypes.byref(i));return(k32.GetTickCount()-i.t)/1000.0
    def right_click_center():
        try:
            w,h=u32.GetSystemMetrics(0),u32.GetSystemMetrics(1)
            u32.SetCursorPos(w//2,h//2);u32.mouse_event(0x0008,0,0,0,0);time.sleep(0.02);u32.mouse_event(0x0010,0,0,0,0);return True
        except: return False
    def press_key(key):
        try:
            vk=ord(key.upper());sc=u32.MapVirtualKeyW(vk,0)
            u32.keybd_event(vk,sc,0,0);time.sleep(0.02);u32.keybd_event(vk,sc,2,0);return True
        except: return False
else:
    def find_game_hwnd():return 0
    def game_focused():return False
    def idle_secs():return 0
    def right_click_center():return False
    def press_key(k):return False

# ═══════════════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════════════
class Config:
    ROLES=['TOP','JUNGLE','MIDDLE','BOTTOM','UTILITY']
    ROLE_KEYS=['pick_id','pick_name','pick_img','backup_id','backup_name','backup_img',
               'ban_id','ban_name','ban_img','spell1_id','spell1_name','spell1_img',
               'spell2_id','spell2_name','spell2_img','rune_id','rune_name','rune_data',
               'backup_rune_id','backup_rune_name','backup_rune_data',
               'backup_spell1_id','backup_spell1_name','backup_spell1_img',
               'backup_spell2_id','backup_spell2_name','backup_spell2_img']
    GLOBAL_KEYS=['chat_on','chat_msg','auto_accept','afk_on','afk_threshold',
                 'auto_pick','auto_ban','auto_spells','auto_runes','auto_items','sound_alert',
                 'light_mode','lite_mode','favorites','auto_minimize','region','build_source']
    def __init__(self):
        self.lock=threading.Lock();self.roles={}
        for r in self.ROLES:
            self.roles[r]={}
            for k in self.ROLE_KEYS: self.roles[r][k]='None' if 'name' in k else None
        self.chat_on=False;self.chat_msg="GLHF";self.auto_accept=True;self.afk_on=False;self.afk_threshold=30
        self.auto_pick=True;self.auto_ban=True;self.auto_spells=False;self.auto_runes=False;self.auto_items=False;self.sound_alert=True
        self.light_mode=False;self.lite_mode=False;self.favorites=[];self.auto_minimize=False;self.region='eune';self.build_source=''
    def snap(self,role='TOP'):
        with self.lock:
            d=dict(self.roles.get(role,self.roles['TOP']));d.update({k:getattr(self,k) for k in self.GLOBAL_KEYS});return d
    def set_role(self,role,key,val):
        with self.lock:
            if role in self.roles: self.roles[role][key]=val
    def get_role(self,role,key):
        with self.lock: return self.roles.get(role,{}).get(key)
    def save(self):
        try:
            with self.lock: d={'roles':self.roles};d.update({k:getattr(self,k) for k in self.GLOBAL_KEYS})
            with open("lol_config.json",'w') as f: json.dump(d,f,indent=2)
        except: pass
    def load(self):
        try:
            if not os.path.exists("lol_config.json"): return False
            with open("lol_config.json") as f: d=json.load(f)
            with self.lock:
                if 'roles' in d:
                    for role in self.ROLES:
                        if role in d['roles']:
                            for k,v in d['roles'][role].items():
                                if k in self.ROLE_KEYS: self.roles[role][k]=v
                for k in self.GLOBAL_KEYS:
                    if k in d: setattr(self,k,d[k])
            return True
        except: return False

# ═══════════════════════════════════════════════════════════════
#  ENGINE
# ═══════════════════════════════════════════════════════════════
class Engine(threading.Thread):
    def __init__(self,cfg,log):
        super().__init__(daemon=True)
        self.cfg=cfg;self.log=log;self.session=None;self.connected=False;self.summoner=""
        self.phase="—";self.accepted=0;self.stop_flag=threading.Event();self._done=set()
        self.detected_role="TOP";self.cs_timer_phase="";self.cs_time_left=0
        # Session stats
        self.stats={'accepts':0,'bans':0,'picks':0,'dodges':0,'games':0}
        self.queue_start=None;self.queue_time=0
        # Summoner info
        self.rank="";self.level=0;self.lp=0;self.wr=""
        self._warned_timer=False
        # Live champ select tracking
        self.cs_allies=[];self.cs_enemies=[];self.cs_bans=[]
        self.pause_pick=False
    def stop(self):self.stop_flag.set()
    def run(self):
        while not self.stop_flag.is_set():
            try:
                if not self.connected:self._conn();self.stop_flag.wait(3);continue
                pd=api_get(self.session,"/lol-gameflow/v1/gameflow-phase")
                if pd is None:self.log("Connection lost");self.connected=False;self.session=None;continue
                old_phase=self.phase;self.phase=str(pd).strip('"')
                # Track queue time
                if self.phase in ("Matchmaking","ReadyCheck"):
                    if not self.queue_start:self.queue_start=time.time()
                    self.queue_time=int(time.time()-self.queue_start)
                else:
                    if self.queue_start and self.phase!="Matchmaking":self.queue_start=None
                    self.queue_time=0
                # Track game count
                if old_phase=="ChampSelect" and self.phase=="InProgress":
                    self.stats['games']+=1
                if self.phase=="ReadyCheck":self._ready()
                elif self.phase=="ChampSelect":self._cs()
                else:
                    self._done.clear();self._warned_timer=False;self.pause_pick=False
                    if hasattr(self,'_cs_enter_time'):del self._cs_enter_time
                self.stop_flag.wait(0.5)
            except Exception as e:self.log(f"Error: {e}");self.stop_flag.wait(2)

    def _conn(self):
        self.log("Searching for client...")
        p,t,m=find_lcu()
        if not p:self.log(f"Not found ({m})");return
        s=mk_session(p,t);d=api_get(s,"/lol-summoner/v1/current-summoner")
        if d and 'displayName' in d:
            self.session=s;self.summoner=d['displayName'];self.connected=True
            self.level=d.get('summonerLevel',0)
            self.log(f"[SUCCESS] Connected: {self.summoner} (Lvl {self.level})")
            # Build perk map from live client (always current patch)
            if build_perk_map_from_lcu(s):
                self.log(f"[SUCCESS] Loaded {len(PERK_MAP)} perks from client")
            else:
                build_perk_map()
                self.log(f"[SUCCESS] Loaded {len(PERK_MAP)} perks from ddragon")
            # Fetch ranked info
            try:
                ranked=api_get(s,"/lol-ranked/v1/current-ranked-stats")
                if ranked:
                    for q in ranked.get('queues',[]):
                        if q.get('queueType')=='RANKED_SOLO_5x5':
                            tier=q.get('tier','').capitalize()
                            div=q.get('division','')
                            self.lp=q.get('leaguePoints',0)
                            wins=q.get('wins',0);losses=q.get('losses',0)
                            self.rank=f"{tier} {div}" if tier else "Unranked"
                            self.wr=f"{wins*100//(wins+losses)}%" if (wins+losses)>0 else ""
                            self.log(f"[SUCCESS] Rank: {self.rank} · {self.lp} LP · {self.wr} WR")
                            break
            except:pass
        else:self.log("Waiting for login...")

    def _ready(self):
        if not self.cfg.auto_accept:return
        d=api_get(self.session,"/lol-matchmaking/v1/ready-check")
        if d and d.get('state')=='InProgress' and d.get('playerResponse')=='None':
            if api_post(self.session,"/lol-matchmaking/v1/ready-check/accept") in (200,204):
                self.accepted+=1;self.stats['accepts']+=1
                self.log(f"[SUCCESS] Match accepted! (#{self.accepted})")
                if self.cfg.sound_alert:
                    try:
                        import winsound;winsound.Beep(800,200);time.sleep(0.05);winsound.Beep(1200,200)
                    except:pass

    def _cs(self):
        try:
            r=self.session.get(f"{self.session._base}/lol-champ-select/v1/session",timeout=2)
            if r.status_code!=200:return
            ses=r.json()
        except:return
        me=ses.get('localPlayerCellId')
        # Role detection
        for m in ses.get('myTeam',[]):
            if m.get('cellId')==me:
                pos=m.get('assignedPosition','').upper()
                rm={'TOP':'TOP','JUNGLE':'JUNGLE','MIDDLE':'MIDDLE','BOTTOM':'BOTTOM','UTILITY':'UTILITY',
                    'MID':'MIDDLE','ADC':'BOTTOM','SUPPORT':'UTILITY','BOT':'BOTTOM','SUP':'UTILITY'}
                det=rm.get(pos,'TOP')
                if det!=self.detected_role:self.detected_role=det;self.log(f"[SUCCESS] Role: {det}")
                break
        snap=self.cfg.snap(self.detected_role)
        timer=ses.get('timer',{});self.cs_timer_phase=timer.get('phase','');self.cs_time_left=timer.get('adjustedTimeLeftInPhase',0)//1000
        
        # Track live picks and bans
        allies=[];enemies=[];bans=[]
        for m2 in ses.get('myTeam',[]):
            cid=m2.get('championId',0)
            pos=m2.get('assignedPosition','')
            is_me=m2.get('cellId')==me
            allies.append({"champId":cid,"position":pos.upper(),"isMe":is_me,"summonerId":m2.get('summonerId',0)})
        for m2 in ses.get('theirTeam',[]):
            cid=m2.get('championId',0)
            enemies.append({"champId":cid,"position":''})
        for grp in ses.get('actions',[]):
            for act in grp:
                if act.get('type')=='ban' and act.get('completed') and act.get('championId'):
                    bans.append(act['championId'])
        self.cs_allies=allies;self.cs_enemies=enemies;self.cs_bans=list(set(bans))
        
        if not hasattr(self,'_cs_enter_time'):self._cs_enter_time=time.time()
        secs_in=time.time()-self._cs_enter_time
        my_ban=my_pick=None
        for grp in ses.get('actions',[]):
            for act in grp:
                if act.get('actorCellId')!=me:continue
                if act.get('type')=='ban' and not act.get('completed'):my_ban=act
                elif act.get('type')=='pick' and not act.get('completed'):my_pick=act
        # Unavailable champs
        unavail=set()
        for grp in ses.get('actions',[]):
            for act in grp:
                if act.get('type')=='ban' and act.get('completed') and act.get('championId'):unavail.add(act['championId'])
        for m2 in ses.get('myTeam',[])+ses.get('theirTeam',[]):
            cid=m2.get('championId',0)
            if cid and m2.get('cellId')!=me:unavail.add(cid)
        pick_id=snap.get('pick_id');pick_name=snap.get('pick_name','None');used_backup=False
        if pick_id and int(pick_id) in unavail:
            if snap.get('backup_id'):
                self.log(f"{pick_name} taken → {snap['backup_name']}");pick_id=snap['backup_id'];pick_name=snap['backup_name'];used_backup=True
            else:pick_id=None
        ban_ready=my_ban and my_ban.get('isInProgress',False)
        pick_ready=my_pick and my_pick.get('isInProgress',False)
        # Timer warning sound when < 5 seconds on YOUR turn
        if self.cs_time_left<=5 and self.cs_time_left>0 and (pick_ready or ban_ready) and not self._warned_timer:
            self._warned_timer=True
            if self.cfg.sound_alert:
                try:
                    import winsound;winsound.Beep(1000,100);time.sleep(0.05);winsound.Beep(1000,100)
                except:pass
        elif self.cs_time_left>5:self._warned_timer=False
        # HOVER PICK
        if my_pick and pick_id and my_pick['id'] not in self._done:
            about_to_ban=(ban_ready and snap['ban_id'] and my_ban['id'] not in self._done and self.cs_timer_phase not in ('PLANNING','') and secs_in>=8)
            if not about_to_ban:
                try:self.session.patch(f"{self.session._base}/lol-champ-select/v1/session/actions/{my_pick['id']}",json={"championId":int(pick_id)},timeout=2)
                except:pass
        # BAN
        if ban_ready and snap['ban_id'] and my_ban['id'] not in self._done and snap.get('auto_ban',True):
            if self.cs_timer_phase in ('PLANNING',''):return
            if secs_in<8:return
            aid=my_ban['id'];cid=int(snap['ban_id']);url=f"{self.session._base}/lol-champ-select/v1/session/actions/{aid}"
            try:self.session.patch(url,json={"championId":cid},timeout=3)
            except:return
            time.sleep(0.4)
            try:
                r2=self.session.patch(url,json={"championId":cid,"completed":True},timeout=3)
                if r2.status_code in (200,204):
                    self._done.add(aid);self.stats['bans']+=1;self.log(f"[SUCCESS] Banned {snap['ban_name']}")
                    if my_pick and pick_id and my_pick['id'] not in self._done:
                        time.sleep(0.3)
                        try:self.session.patch(f"{self.session._base}/lol-champ-select/v1/session/actions/{my_pick['id']}",json={"championId":int(pick_id)},timeout=2)
                        except:pass
            except:pass
        # PICK
        if pick_ready and pick_id and my_pick['id'] not in self._done and snap.get('auto_pick',True) and not self.pause_pick:
            aid=my_pick['id'];cid=int(pick_id);url=f"{self.session._base}/lol-champ-select/v1/session/actions/{aid}"
            try:self.session.patch(url,json={"championId":cid},timeout=3)
            except:pass
            time.sleep(0.3)
            try:
                r=self.session.patch(url,json={"championId":cid,"completed":True},timeout=3)
                if r.status_code in (200,204):
                    self._done.add(aid);self.stats['picks']+=1;self.log(f"[SUCCESS] Locked {pick_name}")
                    time.sleep(0.5);self._after_pick(snap,used_backup)
            except:pass

    def _after_pick(self,snap,used_backup=False):
        if snap.get('auto_spells',True):
            sd={}
            if used_backup:
                if snap.get('backup_spell1_id'):sd['spell1Id']=snap['backup_spell1_id']
                if snap.get('backup_spell2_id'):sd['spell2Id']=snap['backup_spell2_id']
            if not sd:
                if snap['spell1_id']:sd['spell1Id']=snap['spell1_id']
                if snap['spell2_id']:sd['spell2Id']=snap['spell2_id']
            # Auto-spells fallback per role if none set
            if not sd:
                role_spells={'TOP':(4,12),'JUNGLE':(4,11),'MIDDLE':(4,14),'BOTTOM':(4,7),'UTILITY':(4,14)}
                s1,s2=role_spells.get(self.detected_role,(4,14))
                sd={'spell1Id':s1,'spell2Id':s2}
                self.log(f"[SUCCESS] Auto-spells: {self.detected_role} defaults")
            if sd:
                try:self.session.patch(f"{self.session._base}/lol-champ-select/v1/session/my-selection",json=sd,timeout=2);self.log("[SUCCESS] Spells set")
                except:pass
        if snap.get('auto_runes',True):
            rune_data = snap.get('backup_rune_data') if used_backup else snap.get('rune_data')
            rune_id = snap.get('backup_rune_id') if used_backup else snap.get('rune_id')
            # AUTO-PUSH: if no rune configured, fetch first recommended from op.gg
            if not rune_data and not rune_id:
                champ_img = snap.get('backup_img') if used_backup else snap.get('pick_img')
                champ_id = snap.get('backup_id') if used_backup else snap.get('pick_id')
                if champ_img and champ_id:
                    self.log("[DEBUG] No rune set — auto-fetching...")
                    try:cid=int(champ_id)
                    except:cid=0
                    if cid:
                        recs=fetch_recommended_runes(self.session,cid,self.detected_role,champ_key=champ_img,champ_tags=None,log=self.log,source_pref=self.cfg.build_source)
                        if recs:
                            rune_data=recs[0]
                            self.log(f"[SUCCESS] Auto-found: {rune_data.get('name','')}")
            # Write rune data to page
            if rune_data and isinstance(rune_data,dict) and 'primaryStyleId' in rune_data:
                pages=fetch_rune_pages(self.session)
                champ_nm=snap.get('backup_name') if used_backup else snap.get('pick_name','?')
                if pages:
                    if write_runes_to_page(self.session,pages[0]['id'],rune_data,log=self.log,champ_name=champ_nm):
                        self.log(f"[SUCCESS] Runes imported: {rune_data.get('name','')}")
                    else:self.log("[DEBUG] Rune write failed")
            elif rune_id:
                try:self.session.put(f"{self.session._base}/lol-perks/v1/currentpage",data=str(rune_id),
                                    headers={"Content-Type":"application/json"},timeout=2);self.log("[SUCCESS] Runes applied")
                except:pass
        if snap['chat_on'] and snap['chat_msg']:
            time.sleep(0.3)
            try:
                convs=api_get(self.session,"/lol-chat/v1/conversations") or []
                for c in convs:
                    if c.get('type')=='championSelect':
                        self.session.post(f"{self.session._base}/lol-chat/v1/conversations/{c['id']}/messages",json={"body":snap['chat_msg']},timeout=2)
                        self.log(f"Chat: {snap['chat_msg']}");break
            except:pass
        # AUTO-IMPORT ITEMS
        if snap.get('auto_items',True):
            champ_img=snap.get('backup_img') if used_backup else snap.get('pick_img')
            raw_id=snap.get('backup_id') if used_backup else snap.get('pick_id')
            champ_nm=snap.get('backup_name') if used_backup else snap.get('pick_name','?')
            if champ_img and raw_id:
                try:champ_id_val=int(raw_id)
                except:champ_id_val=0
                if champ_id_val:
                    items=fetch_recommended_items(self.session,champ_id_val,self.detected_role,champ_key=champ_img,log=self.log,source_pref=self.cfg.build_source)
                if items:
                    sid=self._get_summoner_id()
                    if sid:write_item_set(self.session,sid,champ_id_val,champ_nm,items,log=self.log)

    def _get_summoner_id(self):
        try:
            d=api_get(self.session,"/lol-summoner/v1/current-summoner")
            return d.get('summonerId') or d.get('accountId')
        except:return None

    def dodge(self):
        """Quit champion select."""
        if self.session and self.phase=="ChampSelect":
            try:
                self.session.post(f"{self.session._base}/lol-login/v1/session/invoke",
                    json={"destination":"lcdsServiceProxy","method":"call","args":["","teambuilder-draft","quitV2",""]},timeout=3)
                self.log("[SUCCESS] Dodged!")
            except:
                try:api_post(self.session,"/lol-champ-select/v1/session/my-selection/reroll")
                except:self.log("[DEBUG] Dodge failed")

class AntiAfk(threading.Thread):
    def __init__(self,cfg,log,engine):
        super().__init__(daemon=True);self.cfg=cfg;self.log=log;self.engine=engine
        self.stop_flag=threading.Event();self.status="Off"
    def stop(self):self.stop_flag.set()
    def run(self):
        while not self.stop_flag.is_set():
            try:
                if not self.cfg.afk_on:self.status="Off";self.stop_flag.wait(1);continue
                if not self.engine.connected or self.engine.phase!="InProgress":
                    self.status="Waiting...";self.stop_flag.wait(2);continue
                if not find_game_hwnd():self.status="No window";self.stop_flag.wait(2);continue
                if not game_focused():self.status="Unfocused";self.stop_flag.wait(1);continue
                idle=idle_secs();thresh=max(5,self.cfg.afk_threshold)
                if idle>=thresh:
                    # Always press Y (lock camera) then right-click
                    press_key('y')
                    self.stop_flag.wait(0.2)
                    if right_click_center():self.status=f"Y+Click ({int(idle)}s)"
                    else:self.status="Click failed"
                    self.stop_flag.wait(2)
                else:
                    self.status=f"Idle {int(idle)}/{thresh}s";self.stop_flag.wait(0.5)
            except:self.stop_flag.wait(2)

# ═══════════════════════════════════════════════════════════════
#  API BRIDGE
# ═══════════════════════════════════════════════════════════════
class Api:
    def __init__(self):
        self.cfg=Config();self.cfg.load();self.logs=[];self.engine=None;self.afk=None
        self.champs=[];self.spells=[];self.ddragon_ver=DDRAGON_VER;self.rune_data={}
        self._init()
        threading.Thread(target=self._load,daemon=True).start()
    def _log(self,msg):
        ts=time.strftime("%H:%M:%S")
        # Skip repetitive debug messages
        if "[DEBUG] Fetching runes" in msg or "[DEBUG] Fetching items" in msg:
            if self.logs and any(msg in l.get('msg','') for l in self.logs[-3:]):return
        self.logs.append({"time":ts,"msg":msg,"type":"success" if "[SUCCESS]" in msg else ("debug" if "[DEBUG]" in msg else "info")})
        if len(self.logs)>80:self.logs=self.logs[-80:]
    def _init(self):
        self.engine=Engine(self.cfg,self._log);self.engine.start()
        self.afk=AntiAfk(self.cfg,self._log,self.engine);self.afk.start()
    def _load(self):
        self._log("[SUCCESS] Initialising Hextech Draft v3...")
        self.champs=fetch_champions();self.spells=fetch_spells();self.ddragon_ver=DDRAGON_VER
        self.rune_data=fetch_runes_reforged()
        self._log(f"[SUCCESS] Loaded {len(self.champs)} champions (patch {DDRAGON_VER})")
        self._log(f"[SUCCESS] Loaded {len(self.rune_data.get('perks',{}))} rune perks")
        self._log("[SUCCESS] Ready.")

    def get_status(self):
        return json.dumps({
            "connected":self.engine.connected if self.engine else False,
            "summoner":self.engine.summoner if self.engine else "",
            "phase":self.engine.phase if self.engine else "—",
            "role":self.engine.detected_role if self.engine else "TOP",
            "accepted":self.engine.accepted if self.engine else 0,
            "afk":self.afk.status if self.afk else "Off",
            "timer_phase":self.engine.cs_timer_phase if self.engine else "",
            "time_left":self.engine.cs_time_left if self.engine else 0,
            "stats":self.engine.stats if self.engine else {},
            "queue_time":self.engine.queue_time if self.engine else 0,
            "rank":self.engine.rank if self.engine else "",
            "level":self.engine.level if self.engine else 0,
            "lp":self.engine.lp if self.engine else 0,
            "wr":self.engine.wr if self.engine else "",
            "allies":self.engine.cs_allies if self.engine else [],
            "enemies":self.engine.cs_enemies if self.engine else [],
            "bans":self.engine.cs_bans if self.engine else [],
            "pause_pick":self.engine.pause_pick if self.engine else False,
            "logs":self.logs[-12:]
        })
    def get_config(self,role): return json.dumps(self.cfg.snap(role))
    def get_champions(self): return json.dumps(self.champs)
    def get_spells(self): return json.dumps(self.spells)
    def get_ddragon_ver(self): return self.ddragon_ver
    def get_rune_data(self): return json.dumps(self.rune_data)
    def get_rune_pages(self, target='rune', role=None):
        results=[]
        if self.engine and self.engine.session:
            use_role=role or self.engine.detected_role
            if target=='backup_rune':
                champ_id=self.cfg.get_role(use_role,'backup_id')
                champ_img=self.cfg.get_role(use_role,'backup_img')
                champ_name=self.cfg.get_role(use_role,'backup_name') or '?'
            else:
                champ_id=self.cfg.get_role(use_role,'pick_id')
                champ_img=self.cfg.get_role(use_role,'pick_img')
                champ_name=self.cfg.get_role(use_role,'pick_name') or '?'
            champ_tags=None
            for c in self.champs:
                if str(c.get('id'))==str(champ_id):champ_tags=c.get('tags',[]);break
            if champ_id:
                label=champ_name.upper() if champ_name and champ_name!='None' else '?'
                self._log(f"[DEBUG] Fetching runes for {label} ({champ_id}) / {role}")
                recs=fetch_recommended_runes(self.engine.session,int(champ_id),role,champ_key=champ_img,champ_tags=champ_tags,log=self._log,source_pref=self.cfg.build_source)
                self._log(f"[DEBUG] Found {len(recs)} recommended rune pages")
                for r in recs:
                    nm=r['name']
                    if label!='?': nm=f"{nm} ({label})"
                    results.append({"id":None,"name":nm,"source":r.get('source','recommended'),"data":r})
            for p in fetch_rune_pages(self.engine.session):
                pids=p.get('selectedPerkIds',[])
                if pids and len(pids)>=4 and p.get('primaryStyleId'):
                    results.append({"id":p['id'],"name":p['name'],"source":"user","data":{
                        "name":p['name'],"primaryStyleId":p.get('primaryStyleId'),
                        "subStyleId":p.get('subStyleId'),"selectedPerkIds":pids}})
        return json.dumps(results)

    def set_setting(self,role,key,value):
        if value=="__null__":value=None
        if key in ('pick_id','backup_id','ban_id','spell1_id','spell2_id','rune_id','backup_rune_id','backup_spell1_id','backup_spell2_id') and value is not None:
            try:value=int(value)
            except:pass
        if key in ('rune_data','backup_rune_data') and isinstance(value,str):
            try:value=json.loads(value)
            except:value=None
        self.cfg.set_role(role,key,value);self.cfg.save()

    def set_global(self,key,value):
        if key in ('auto_accept','chat_on','afk_on','auto_pick','auto_ban','auto_spells','auto_runes','auto_items','sound_alert','light_mode','lite_mode','auto_minimize'):
            setattr(self.cfg,key,value)
        elif key=='chat_msg':self.cfg.chat_msg=value
        elif key=='region':self.cfg.region=str(value).lower()
        elif key=='build_source':self.cfg.build_source=str(value).lower()
        elif key=='afk_threshold':
            try:self.cfg.afk_threshold=max(5,min(120,int(value)))
            except:pass
        self.cfg.save()

    def get_version(self):
        return APP_VERSION
    def get_region(self):
        return self.cfg.region or 'eune'
    def get_build_source(self):
        return self.cfg.build_source or ''
    def toggle_pause_pick(self):
        if self.engine:
            self.engine.pause_pick=not self.engine.pause_pick
            self._log(f"[DEBUG] Auto-pick {'PAUSED' if self.engine.pause_pick else 'RESUMED'}")
            return self.engine.pause_pick
        return False

    def check_update(self):
        result = check_for_update(log=self._log)
        return json.dumps(result)

    def do_update(self, exe_url):
        result = download_update(exe_url, log=self._log)
        if result and IS_WINDOWS and getattr(sys,'frozen',False) and str(result).endswith('.bat'):
            self._log("[SUCCESS] Applying update — app will restart...")
            subprocess.Popen(['cmd','/c',str(result)], creationflags=0x08000000)
            time.sleep(1)
            os._exit(0)
        return json.dumps({"success":bool(result)})

    def dodge(self):
        if self.engine:
            self.engine.dodge()
            self.engine.stats['dodges']+=1

    def swap_spells(self, role):
        """Swap spell 1 and spell 2 for a role."""
        s1_id=self.cfg.get_role(role,'spell1_id');s1_name=self.cfg.get_role(role,'spell1_name');s1_img=self.cfg.get_role(role,'spell1_img')
        s2_id=self.cfg.get_role(role,'spell2_id');s2_name=self.cfg.get_role(role,'spell2_name');s2_img=self.cfg.get_role(role,'spell2_img')
        self.cfg.set_role(role,'spell1_id',s2_id);self.cfg.set_role(role,'spell1_name',s2_name);self.cfg.set_role(role,'spell1_img',s2_img)
        self.cfg.set_role(role,'spell2_id',s1_id);self.cfg.set_role(role,'spell2_name',s1_name);self.cfg.set_role(role,'spell2_img',s1_img)
        self.cfg.save()

    def swap_backup_spells(self, role):
        """Swap backup spell 1 and backup spell 2."""
        s1_id=self.cfg.get_role(role,'backup_spell1_id');s1_name=self.cfg.get_role(role,'backup_spell1_name');s1_img=self.cfg.get_role(role,'backup_spell1_img')
        s2_id=self.cfg.get_role(role,'backup_spell2_id');s2_name=self.cfg.get_role(role,'backup_spell2_name');s2_img=self.cfg.get_role(role,'backup_spell2_img')
        self.cfg.set_role(role,'backup_spell1_id',s2_id);self.cfg.set_role(role,'backup_spell1_name',s2_name);self.cfg.set_role(role,'backup_spell1_img',s2_img)
        self.cfg.set_role(role,'backup_spell2_id',s1_id);self.cfg.set_role(role,'backup_spell2_name',s1_name);self.cfg.set_role(role,'backup_spell2_img',s1_img)
        self.cfg.save()

    def toggle_favorite(self, champ_id):
        """Add/remove champion from favorites."""
        cid=int(champ_id)
        if cid in self.cfg.favorites:self.cfg.favorites.remove(cid)
        else:self.cfg.favorites.append(cid)
        self.cfg.save()
        return json.dumps(self.cfg.favorites)

    def get_favorites(self):
        return json.dumps(self.cfg.favorites or [])

    def get_mastery(self, champ_id):
        if self.engine and self.engine.session:
            sid=self.engine._get_summoner_id()
            if sid:
                m=fetch_champion_mastery(self.engine.session,sid,int(champ_id))
                if m:return json.dumps(m)
        return json.dumps(None)

    def import_items_now(self, role):
        """Manually trigger item import for current role's pick."""
        if not self.engine or not self.engine.session:return False
        pick_img=self.cfg.get_role(role,'pick_img')
        pick_id=self.cfg.get_role(role,'pick_id')
        pick_name=self.cfg.get_role(role,'pick_name')
        if not pick_img or not pick_id:return False
        items=fetch_recommended_items(self.engine.session,int(pick_id),role,champ_key=pick_img,log=self._log,source_pref=self.cfg.build_source)
        if items:
            sid=self.engine._get_summoner_id()
            if sid:return write_item_set(self.engine.session,sid,int(pick_id),pick_name,items,log=self._log)
        return False

    def random_from_favorites(self):
        """Pick a random champion from favorites."""
        import random
        favs=self.cfg.favorites or []
        if not favs:return json.dumps(None)
        cid=random.choice(favs)
        for c in self.champs:
            if c.get('id')==cid:return json.dumps(c)
        return json.dumps(None)

    def copy_role(self, from_role, to_role):
        """Copy all settings from one role to another."""
        for k in self.cfg.ROLE_KEYS:
            val=self.cfg.get_role(from_role,k)
            self.cfg.set_role(to_role,k,val)
        self.cfg.save()
        self._log(f"[SUCCESS] Copied {from_role} → {to_role}")

    def get_ban_suggestions(self, role):
        """Get common ban suggestions per role from op.gg."""
        pos_map={'TOP':'top','JUNGLE':'jungle','MIDDLE':'mid','BOTTOM':'adc','UTILITY':'support'}
        pos=pos_map.get(role,'top')
        try:
            url=f"https://www.op.gg/champions?position={pos}&tier=gold_plus"
            resp=requests.get(url,timeout=8,headers={
                'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36','Accept':'text/html'})
            if resp.status_code!=200:return json.dumps([])
            # Find champion names with high ban rates
            bans=re.findall(r'"ban_rate":\s*([\d.]+)[^}]*"name":\s*"([^"]+)"',resp.text)
            if not bans:
                bans=re.findall(r'"name":\s*"([^"]+)"[^}]*"ban_rate":\s*([\d.]+)',resp.text)
                bans=[(b,a) for a,b in bans]
            results=[]
            for rate,name in sorted(bans,key=lambda x:float(x[0]),reverse=True)[:8]:
                for c in self.champs:
                    if c['name'].lower()==name.lower():
                        results.append({"id":c['id'],"name":c['name'],"img":c['img'],"banRate":float(rate)})
                        break
            return json.dumps(results)
        except:return json.dumps([])

    def get_match_history(self):
        """Get recent match history from LCU."""
        if not self.engine or not self.engine.session:return json.dumps([])
        try:
            d=api_get(self.engine.session,"/lol-match-history/v1/products/lol/current-summoner/matches?begIndex=0&endIndex=10")
            if not d or 'games' not in d:return json.dumps([])
            games=[]
            for g in d['games'].get('games',[])[:10]:
                p=g.get('participants',[{}])[0]
                stats=p.get('stats',{})
                games.append({
                    "champId":p.get('championId',0),
                    "win":stats.get('win',False),
                    "kills":stats.get('kills',0),
                    "deaths":stats.get('deaths',0),
                    "assists":stats.get('assists',0),
                    "cs":stats.get('totalMinionsKilled',0)+stats.get('neutralMinionsKilled',0),
                    "duration":g.get('gameDuration',0),
                    "queueId":g.get('queueId',0),
                    "timestamp":g.get('gameCreation',0)
                })
            return json.dumps(games)
        except:return json.dumps([])

    def get_recently_played(self):
        """Get list of champion IDs played recently."""
        if not self.engine or not self.engine.session:return json.dumps([])
        try:
            d=api_get(self.engine.session,"/lol-match-history/v1/products/lol/current-summoner/matches?begIndex=0&endIndex=20")
            if not d or 'games' not in d:return json.dumps([])
            champs=[]
            seen=set()
            for g in d['games'].get('games',[]):
                cid=g.get('participants',[{}])[0].get('championId',0)
                if cid and cid not in seen:
                    seen.add(cid)
                    champs.append(cid)
            return json.dumps(champs[:15])
        except:return json.dumps([])

    def get_champ_winrate(self, champ_id):
        """Get personal winrate with a specific champion from match history."""
        if not self.engine or not self.engine.session:return json.dumps(None)
        try:
            d=api_get(self.engine.session,"/lol-match-history/v1/products/lol/current-summoner/matches?begIndex=0&endIndex=50")
            if not d or 'games' not in d:return json.dumps(None)
            wins=0;total=0
            for g in d['games'].get('games',[]):
                p=g.get('participants',[{}])[0]
                if p.get('championId')==int(champ_id):
                    total+=1
                    if p.get('stats',{}).get('win'):wins+=1
            if total==0:return json.dumps(None)
            return json.dumps({"wins":wins,"total":total,"rate":round(wins*100/total,1)})
        except:return json.dumps(None)

    def set_champ_note(self, champ_id, note):
        """Save a personal note for a champion."""
        notes={}
        try:
            if os.path.exists("hextech_notes.json"):
                with open("hextech_notes.json") as f:notes=json.load(f)
        except:pass
        notes[str(champ_id)]=note
        try:
            with open("hextech_notes.json",'w') as f:json.dump(notes,f)
        except:pass

    def get_champ_note(self, champ_id):
        """Get personal note for a champion."""
        try:
            if os.path.exists("hextech_notes.json"):
                with open("hextech_notes.json") as f:notes=json.load(f)
                return notes.get(str(champ_id),'')
        except:pass
        return ''

    def minimize_window(self):
        """Minimize the pywebview window."""
        try:
            import webview
            for w in webview.windows:w.minimize()
        except:pass

    def lookup_team(self):
        """Get summoner names of all teammates for multi-search."""
        if not self.engine or not self.engine.session:return json.dumps([])
        names=[]
        for ally in self.engine.cs_allies:
            sid=ally.get('summonerId')
            if sid:
                try:
                    d=api_get(self.engine.session,f"/lol-summoner/v1/summoners/{sid}")
                    if d and d.get('displayName'):
                        names.append(d['displayName'])
                except:pass
        return json.dumps(names)

    def get_live_game_info(self):
        """Get current game info from gameflow."""
        if not self.engine or not self.engine.session:return json.dumps(None)
        try:
            d=api_get(self.engine.session,"/lol-gameflow/v1/session")
            if d:
                gc=d.get('gameData',{})
                return json.dumps({
                    "map":gc.get('queue',{}).get('mapId',11),
                    "mode":gc.get('queue',{}).get('gameMode',''),
                    "queue":gc.get('queue',{}).get('description',''),
                    "teamSize":gc.get('teamSize',5)
                })
        except:pass
        return json.dumps(None)

    def export_config(self):
        try:
            with open("lol_config.json",'r') as f: return f.read()
        except: return "{}"

    def import_config(self, data):
        try:
            d=json.loads(data)
            with open("lol_config.json",'w') as f: json.dump(d,f,indent=2)
            self.cfg.load()
            self._log("[SUCCESS] Config imported!")
            return True
        except: return False

    def reset_config(self):
        try:
            if os.path.exists("lol_config.json"): os.remove("lol_config.json")
            self.cfg.__init__()
            self._log("[SUCCESS] Config reset to defaults!")
            return True
        except: return False

# ═══════════════════════════════════════════════════════════════
#  HTML
# ═══════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════
#  HTML — Premium Hextech UI (design tokens from Emergent)
# ═══════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════
#  HTML — Hextech Draft UI
# ═══════════════════════════════════════════════════════════════


HTML=r"""<!DOCTYPE html><html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Rajdhani:wght@400;500;600;700&family=Orbitron:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root{--bg:#010A13;--panel:#091428;--surface:rgba(9,20,40,0.6);--surfhov:rgba(9,20,40,0.85);--border:rgba(200,170,110,0.2);--borderact:rgba(200,170,110,0.8);--bordercyan:rgba(10,200,185,0.6);--cyan:#0AC8B9;--gold:#C8AA6E;--danger:#FF4E50;--success:#00FF9C;--text:#F0E6D2;--text2:#A09B8C;--textm:#8A8272;--zoom:1}
*{margin:0;padding:0;box-sizing:border-box}
body{background:var(--bg);color:var(--text);font-family:'Rajdhani',sans-serif;font-size:14px;font-weight:500;overflow:hidden;user-select:none;height:100vh}
.app{display:flex;flex-direction:column;height:100vh;gap:5px;padding:5px;position:relative;transform:scale(var(--zoom));transform-origin:top left;width:calc(100%/var(--zoom));height:calc(100vh/var(--zoom))}
.app::before{content:"";position:absolute;inset:0;background:radial-gradient(ellipse at 20% 50%,rgba(10,200,185,.03) 0%,transparent 50%),radial-gradient(ellipse at 80% 20%,rgba(200,170,110,.03) 0%,transparent 50%);pointer-events:none}
.gp{background:rgba(9,20,40,.55);backdrop-filter:blur(16px);border:1px solid var(--border);position:relative;border-radius:8px;box-shadow:0 8px 32px rgba(0,0,0,.4),inset 0 1px 0 rgba(240,230,210,.04)}
.gp::before{content:"";position:absolute;top:0;left:0;right:0;height:1px;background:linear-gradient(90deg,transparent,rgba(200,170,110,.5),transparent);pointer-events:none;border-radius:8px 8px 0 0}
.gc{position:absolute;width:8px;height:8px;border-color:var(--gold);opacity:.4;pointer-events:none}
.gc.tl{top:4px;left:4px;border-top:1px solid;border-left:1px solid}.gc.tr{top:4px;right:4px;border-top:1px solid;border-right:1px solid}
.gc.bl{bottom:4px;left:4px;border-bottom:1px solid;border-left:1px solid}.gc.br{bottom:4px;right:4px;border-bottom:1px solid;border-right:1px solid}
@keyframes scanl{0%{transform:translateY(-100%)}100%{transform:translateY(3000%)}}
.scanl{position:absolute;left:0;right:0;height:2px;background:linear-gradient(90deg,transparent,rgba(10,200,185,.4),transparent);animation:scanl 4s linear infinite;pointer-events:none}
@keyframes shimmer{0%{background-position:200% 0}100%{background-position:-200% 0}}
.gshim{background:linear-gradient(90deg,#C8AA6E,#F0E6D2,#C8AA6E);background-size:200% 100%;-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;animation:shimmer 4s linear infinite}
.hdiv{height:1px;background:linear-gradient(90deg,transparent,rgba(200,170,110,.3),transparent);margin:5px 0}
.hs::-webkit-scrollbar{width:5px}.hs::-webkit-scrollbar-track{background:rgba(1,10,19,.4)}.hs::-webkit-scrollbar-thumb{background:linear-gradient(180deg,rgba(200,170,110,.4),rgba(10,200,185,.4));border-radius:4px}

/* HEADER */
.hdr{display:flex;align-items:center;padding:8px 16px;gap:14px}
.hdr-l h1{font-family:'Orbitron',sans-serif;font-size:18px;font-weight:900;letter-spacing:4px}
.hdr-l .sub{font-family:'JetBrains Mono';font-size:9px;color:var(--textm);letter-spacing:4px;font-weight:600}
.hdr-st{display:flex;align-items:center;gap:8px;margin-left:auto;font-size:12px;font-weight:600}
.dot{width:9px;height:9px;border-radius:50%;background:var(--textm);transition:all .3s}.dot.on{background:var(--cyan);box-shadow:0 0 10px var(--cyan)}
.zc{display:flex;align-items:center;gap:3px;margin-left:6px}
.zb{width:24px;height:24px;border-radius:4px;border:1px solid var(--border);background:transparent;color:var(--text2);font-size:14px;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:all .2s;font-family:'Orbitron';font-weight:700}
.zb:hover{border-color:var(--bordercyan);color:var(--cyan)}
.zp{font-family:'Orbitron';font-size:8px;color:var(--textm);min-width:30px;text-align:center}

/* MAIN 3-COL */
.m3{display:grid;grid-template-columns:235px 1fr 250px;gap:5px;flex:1;min-height:0}
.sh{display:flex;justify-content:space-between;align-items:center;margin-bottom:5px}
.sh h3{font-family:'Orbitron';font-size:9px;font-weight:700;letter-spacing:3px;color:var(--textm)}
.sh .bd{font-family:'JetBrains Mono';font-size:9px;color:var(--text2);font-weight:600}

/* LEFT PANEL */
.tp{display:flex;flex-direction:column;padding:8px;overflow-y:auto}
.slot{display:flex;align-items:center;gap:7px;padding:5px 7px;border:1px solid transparent;border-radius:6px;cursor:pointer;transition:all .2s;margin-bottom:2px}
.slot:hover{background:var(--surfhov);border-color:var(--border)}
.slot.on{border-color:var(--bordercyan);background:rgba(10,200,185,.06)}
.slot .pt{width:36px;height:36px;border-radius:4px;border:2px solid var(--border);background:var(--bg);object-fit:cover;flex-shrink:0}
.slot .pt.emp{opacity:.15}.slot.on .pt{border-color:var(--cyan)}
.si{flex:1;min-width:0}
.si .rl{font-family:'Orbitron';font-size:8px;font-weight:700;letter-spacing:2px;color:var(--textm)}
.si .nm{font-family:'Rajdhani';font-size:13px;font-weight:700;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;text-transform:uppercase;letter-spacing:1px}
.si .nm.emp{color:var(--textm);font-weight:500;font-style:normal;letter-spacing:0}
.you{font-family:'Orbitron';font-size:7px;font-weight:700;color:var(--cyan);background:rgba(10,200,185,.12);padding:1px 5px;border-radius:3px;letter-spacing:1px;margin-left:3px}
.brow{display:flex;gap:4px;flex-wrap:wrap;margin-top:2px}
.bs{width:36px;height:36px;border-radius:4px;border:1px solid var(--border);background:rgba(1,10,19,.5);cursor:pointer;transition:all .2s;overflow:hidden;position:relative}
.bs:hover{border-color:var(--bordercyan)}.bs.on{border-color:var(--cyan);box-shadow:0 0 8px rgba(10,200,185,.15)}
.bs img{width:100%;height:100%;object-fit:cover}
.bs-label{position:absolute;bottom:0;left:0;right:0;font-family:'Orbitron';font-size:6px;font-weight:700;text-align:center;background:rgba(0,0,0,.7);color:var(--textm);padding:1px;letter-spacing:1px}
.srow{display:flex;gap:4px;margin-top:3px}
.ss{width:32px;height:32px;border-radius:4px;border:1px solid var(--border);background:rgba(1,10,19,.5);cursor:pointer;overflow:hidden;transition:all .2s}
.ss:hover{border-color:var(--bordercyan)}.ss img{width:100%;height:100%;object-fit:cover}
.rs{display:flex;align-items:center;gap:6px;padding:4px 7px;border:1px solid var(--border);border-radius:4px;cursor:pointer;margin-top:3px;font-family:'Rajdhani';font-size:12px;font-weight:600;color:var(--text2);transition:all .2s;letter-spacing:.5px}
.rs:hover{border-color:var(--bordercyan);color:var(--text)}
.rune-display{padding:4px;margin-top:3px;border:1px solid var(--border);border-radius:6px;background:rgba(1,10,19,.4)}
.rune-perks{display:flex;flex-wrap:wrap;gap:3px}
.rune-perk{width:26px;height:26px;border-radius:50%;border:1px solid var(--border);background:rgba(1,10,19,.6);overflow:hidden}
.rune-perk img{width:100%;height:100%;object-fit:cover}
.rune-perk.ks{width:34px;height:34px;border-color:var(--bordercyan);box-shadow:0 0 6px rgba(10,200,185,.2)}

/* CENTER: CHAMPION POOL */
.pp{display:flex;flex-direction:column;padding:8px;overflow:hidden}
.pt-top{display:flex;align-items:center;gap:8px;margin-bottom:6px;flex-wrap:wrap}
.pt-top h3{font-family:'Orbitron';font-size:9px;font-weight:700;letter-spacing:3px;color:var(--textm)}
.pcnt{font-family:'JetBrains Mono';font-size:10px;color:var(--text2);margin-right:auto;font-weight:600}
.lkb{font-family:'Orbitron';font-size:8px;font-weight:700;letter-spacing:1px;padding:5px 12px;border-radius:4px;border:1px solid;cursor:pointer;transition:all .2s}
.lkb.ban{border-color:rgba(255,78,80,.3);color:var(--danger);background:rgba(255,78,80,.05)}.lkb.ban:hover{background:rgba(255,78,80,.15)}
.lkb.pick{border-color:var(--bordercyan);color:var(--cyan);background:rgba(10,200,185,.05)}.lkb.pick:hover{background:rgba(10,200,185,.15)}
.lkb.backup{border-color:rgba(200,170,110,.3);color:var(--gold);background:rgba(200,170,110,.05)}.lkb.backup:hover{background:rgba(200,170,110,.15)}
.srch input{width:100%;background:rgba(1,10,19,.7);border:1px solid var(--border);border-radius:4px;color:var(--text);padding:7px 12px;font-size:13px;font-family:'Rajdhani';font-weight:600;outline:none;transition:border-color .2s;letter-spacing:.5px;margin-bottom:5px}
.srch input:focus{border-color:var(--bordercyan)}
.tgs{display:flex;gap:3px;flex-wrap:wrap;margin-bottom:5px}
.tg{padding:3px 10px;font-family:'Orbitron';font-size:7px;font-weight:700;letter-spacing:1px;cursor:pointer;border:1px solid var(--border);border-radius:20px;color:var(--textm);transition:all .2s}
.tg:hover{border-color:rgba(200,170,110,.4);color:var(--text2)}.tg.on{color:var(--gold);border-color:var(--borderact);background:rgba(200,170,110,.08)}
.cg{flex:1;overflow-y:auto;display:grid;grid-template-columns:repeat(auto-fill,minmax(74px,1fr));gap:3px;align-content:flex-start;padding-right:3px}
.ch{text-align:center;cursor:pointer;padding:3px;border:1px solid transparent;border-radius:6px;transition:all .15s}
.ch:hover{border-color:var(--bordercyan);background:rgba(10,200,185,.04);transform:translateY(-1px)}
.ch.sel{border-color:var(--cyan);background:rgba(10,200,185,.08)}
.ch img{width:56px;height:56px;border-radius:4px;border:2px solid rgba(200,170,110,.12);display:block;margin:0 auto 2px;transition:all .2s}
.ch:hover img{border-color:var(--bordercyan);box-shadow:0 0 8px rgba(10,200,185,.15)}
.ch .cn{font-family:'Rajdhani';font-size:10px;font-weight:700;color:var(--textm);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;text-transform:uppercase;letter-spacing:.5px}
.ch:hover .cn{color:var(--text)}
.nr{grid-column:1/-1;text-align:center;padding:30px;font-family:'Orbitron';font-size:10px;color:var(--textm);letter-spacing:3px}

/* RIGHT: PREFS */
.rp{display:flex;flex-direction:column;padding:8px;overflow-y:auto}
.prof{display:flex;align-items:center;gap:10px;padding:10px;background:rgba(1,10,19,.4);border-radius:6px;margin-bottom:6px}
.pav{width:42px;height:42px;border-radius:50%;border:2px solid var(--gold);background:var(--panel);display:flex;align-items:center;justify-content:center;font-family:'Orbitron';font-size:16px;font-weight:900;color:var(--gold)}
.pinf .pnm{font-family:'Rajdhani';font-size:16px;font-weight:700;color:var(--text);text-transform:uppercase;letter-spacing:1px}
.pinf .pdt{font-family:'JetBrains Mono';font-size:9px;color:var(--textm)}
.pr{display:flex;align-items:center;gap:8px;padding:8px 6px;border-radius:6px;transition:background .2s}.pr:hover{background:rgba(1,10,19,.4)}
.pi{flex:1}.pi .pn{font-family:'Rajdhani';font-size:14px;font-weight:700;color:var(--text);letter-spacing:.5px}.pi .pd{font-family:'JetBrains Mono';font-size:8px;color:var(--textm);margin-top:1px}
.sw{width:42px;height:22px;border-radius:11px;background:rgba(1,10,19,.9);border:1px solid var(--textm);cursor:pointer;position:relative;transition:all .3s;flex-shrink:0}
.sw.on{background:var(--cyan);border-color:var(--cyan)}.sw::after{content:'';position:absolute;top:2px;left:2px;width:16px;height:16px;border-radius:50%;background:var(--text);transition:all .3s;box-shadow:0 1px 3px rgba(0,0,0,.4)}.sw.on::after{left:22px;background:var(--bg)}
.hb{font-family:'Orbitron';font-size:7px;font-weight:700;letter-spacing:1px;padding:4px 10px;border-radius:4px;border:1px solid rgba(200,170,110,.3);color:var(--gold);background:rgba(200,170,110,.05);cursor:pointer;transition:all .2s}
.hb:hover{background:rgba(200,170,110,.15)}
.dg{width:100%;padding:8px;margin-top:auto;font-family:'Orbitron';font-size:8px;font-weight:700;letter-spacing:3px;border:1px solid rgba(255,78,80,.25);border-radius:4px;color:rgba(255,78,80,.5);background:rgba(255,78,80,.03);cursor:pointer;transition:all .3s}
.dg:hover{background:rgba(255,78,80,.12);border-color:var(--danger);color:var(--danger)}

/* CONSOLE */
.con{overflow:hidden}
.conh{display:flex;align-items:center;gap:8px;padding:5px 12px;font-family:'Orbitron';font-size:9px;font-weight:700}
.conh .tl{letter-spacing:3px;color:var(--textm)}.conh .ct{color:var(--textm);font-weight:500;font-family:'JetBrains Mono';font-size:9px}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
.conh .lv{color:var(--cyan);display:flex;align-items:center;gap:4px;font-family:'JetBrains Mono';font-size:9px}.conh .lv::before{content:'';width:5px;height:5px;border-radius:50%;background:var(--cyan);box-shadow:0 0 6px var(--cyan);animation:pulse 2s infinite}
.conb{display:flex;gap:12px;padding:3px 12px;font-size:11px;font-weight:600}.conb .cc{color:var(--cyan)}.conb .cp{color:var(--textm)}.conb .ca{color:var(--textm);margin-left:auto}
.la{background:rgba(1,10,19,.8);margin:3px 5px 5px;padding:5px 8px;border-radius:4px;font-family:'JetBrains Mono';font-size:10px;height:70px;overflow-y:auto;border:1px solid var(--bordercyan)}
.ll{margin-bottom:1px;line-height:1.5;display:flex;gap:6px}.ll .ts{color:rgba(10,200,185,.35);flex-shrink:0}.ll .ok{color:var(--success);font-weight:600}.ll .nf{color:var(--textm)}.ll .db{color:var(--gold)}

/* MODAL */
.mbg{display:none;position:fixed;inset:0;background:rgba(1,10,19,.85);backdrop-filter:blur(4px);z-index:100;justify-content:center;align-items:center;transform:scale(var(--zoom));transform-origin:center center}.mbg.show{display:flex}
.mdl{border-radius:10px;width:520px;max-height:480px;display:flex;flex-direction:column;overflow:hidden;box-shadow:0 16px 50px rgba(0,0,0,.5)}
.mh{padding:8px 14px;font-family:'Orbitron';font-size:9px;font-weight:700;letter-spacing:2px;color:var(--gold);display:flex;justify-content:space-between;align-items:center}
.mh button{background:none;border:none;color:var(--textm);cursor:pointer;font-size:14px}.mh button:hover{color:var(--danger)}
.msr{padding:5px 8px}.msr input{width:100%;background:rgba(1,10,19,.7);border:1px solid var(--border);border-radius:4px;color:var(--text);padding:7px 10px;font-size:12px;outline:none;font-family:'Rajdhani';font-weight:600}.msr input:focus{border-color:var(--bordercyan)}
.mls{flex:1;overflow-y:auto;padding:4px 8px}
.mi{display:flex;align-items:center;gap:8px;padding:7px 10px;cursor:pointer;border-radius:6px;transition:all .15s}.mi:hover{background:rgba(10,200,185,.06)}
.mi img{width:32px;height:32px;border-radius:4px;border:1px solid var(--border)}.mi .mn{font-family:'Rajdhani';font-size:13px;font-weight:700;color:var(--text);letter-spacing:.5px}
.mi .src{font-family:'Orbitron';font-size:7px;color:var(--cyan);margin-left:auto;letter-spacing:1px;font-weight:700}
.mi .rpv{display:flex;gap:2px;margin-left:6px}
.mi .rpv img{width:20px;height:20px;border-radius:50%;border:1px solid var(--border)}
.mi .rpv img.ks{width:26px;height:26px;border-color:var(--bordercyan)}

/* SETTINGS GEAR */
.gear-btn{background:none;border:1px solid var(--border);border-radius:4px;color:var(--textm);cursor:pointer;font-size:16px;padding:2px 6px;transition:all .2s;margin-left:6px}
.gear-btn:hover{border-color:var(--bordercyan);color:var(--cyan)}
.settings-overlay{display:none;position:fixed;inset:0;background:rgba(1,10,19,.85);backdrop-filter:blur(4px);z-index:200;justify-content:center;align-items:center;transform:scale(var(--zoom));transform-origin:center center}
.settings-overlay.show{display:flex}
.settings-box{border-radius:10px;width:400px;max-height:500px;display:flex;flex-direction:column;overflow:hidden;box-shadow:0 16px 50px rgba(0,0,0,.5)}
.settings-box .sh2{padding:10px 16px;font-family:'Orbitron';font-size:10px;font-weight:700;letter-spacing:3px;color:var(--gold);display:flex;justify-content:space-between;align-items:center}
.settings-box .sh2 button{background:none;border:none;color:var(--textm);cursor:pointer;font-size:16px}.settings-box .sh2 button:hover{color:var(--danger)}
.settings-body{padding:10px 14px;overflow-y:auto}
.scat{font-family:'Orbitron';font-size:8px;font-weight:700;letter-spacing:3px;color:var(--textm);margin:10px 0 6px;padding-bottom:4px;border-bottom:1px solid rgba(200,170,110,.1)}
.scat:first-child{margin-top:0}
.srow{display:flex;align-items:center;gap:8px;padding:8px 6px;border-radius:6px;transition:background .2s}.srow:hover{background:rgba(1,10,19,.4)}
.srow .si2{flex:1}.srow .si2 .sn{font-family:'Rajdhani';font-size:13px;font-weight:700;color:var(--text)}.srow .si2 .sd{font-family:'JetBrains Mono';font-size:8px;color:var(--textm);margin-top:1px}

/* LIGHT MODE */
body.light{--bg:#e8e4de;--panel:#f5f2ed;--surface:rgba(240,235,225,0.7);--surfhov:rgba(230,225,215,0.9);--border:rgba(120,90,40,0.2);--borderact:rgba(120,90,40,0.6);--bordercyan:rgba(8,140,130,0.5);--cyan:#088a82;--gold:#8a6a2e;--danger:#cc3030;--success:#0a8a4a;--text:#1a1a1a;--text2:#4a4a4a;--textm:#7a7a7a}
body.light .gp{background:rgba(245,242,237,0.85);box-shadow:0 2px 12px rgba(0,0,0,.08),inset 0 1px 0 rgba(255,255,255,.5)}
body.light .gp::before{background:linear-gradient(90deg,transparent,rgba(120,90,40,.3),transparent)}
body.light .gc{border-color:var(--gold);opacity:.3}
body.light .scanl{background:linear-gradient(90deg,transparent,rgba(8,140,130,.2),transparent)}
body.light .gshim{background:linear-gradient(90deg,#6a5020,#3a3020,#6a5020);background-size:200% 100%;-webkit-background-clip:text;background-clip:text}
body.light .la{background:rgba(255,255,255,.6);border-color:rgba(8,140,130,.3)}
body.light .ch img{border-color:rgba(120,90,40,.15)}
body.light .slot .pt{border-color:rgba(120,90,40,.2);background:#f0ede8}
body.light .bs{border-color:rgba(120,90,40,.2);background:rgba(240,235,225,.5)}
body.light .ss{border-color:rgba(120,90,40,.2);background:rgba(240,235,225,.5)}
body.light .sw{background:rgba(200,195,185,.8);border-color:rgba(120,90,40,.3)}
body.light .sw::after{background:#fff}
body.light .sw.on{background:var(--cyan)}
body.light .sw.on::after{background:#f5f2ed}
body.light .srch input{background:rgba(255,255,255,.7);border-color:rgba(120,90,40,.2);color:#1a1a1a}
body.light .tg{border-color:rgba(120,90,40,.2);color:#7a7a7a}
body.light .prof{background:rgba(230,225,215,.6)}
body.light .hdiv{background:linear-gradient(90deg,transparent,rgba(120,90,40,.2),transparent)}
body.light .rs{border-color:rgba(120,90,40,.2)}
body.light .rune-display{background:rgba(230,225,215,.5);border-color:rgba(120,90,40,.15)}

/* LITE MODE — disable expensive effects */
body.lite .gp{backdrop-filter:none;-webkit-backdrop-filter:none;box-shadow:none}
body.lite .scanl{display:none}
body.lite .gshim{animation:none;background:var(--gold);-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
body.lite .app::before{display:none}
body.lite .gc{display:none}
body.lite .gp::before{display:none}
body.lite .conh .lv::before{animation:none}
body.lite .ch:hover{transform:none}
body.lite .dot.on{box-shadow:none}

/* MICRO-INTERACTIONS */
@keyframes clickFlash{0%{box-shadow:0 0 0 0 rgba(10,200,185,.4)}50%{box-shadow:0 0 0 8px rgba(10,200,185,0)}100%{box-shadow:none}}
@keyframes starPop{0%{transform:scale(1)}40%{transform:scale(1.5)}100%{transform:scale(1)}}
@keyframes toastIn{0%{transform:translateY(20px);opacity:0}100%{transform:translateY(0);opacity:1}}
@keyframes toastOut{0%{transform:translateY(0);opacity:1}100%{transform:translateY(-20px);opacity:0}}
@keyframes slotFlash{0%{background:rgba(10,200,185,.15)}100%{background:transparent}}
.lkb:active,.hb:active,.zb:active,.tg:active,.dg:active,.gear-btn:active{transform:scale(0.92);transition:transform 0.05s}
.lkb,.hb,.zb,.gear-btn{transition:all .15s ease}
.dg{transition:all .2s ease}.dg:active{transform:scale(0.97)}
.slot{transition:all .15s ease}.slot:active{transform:scale(0.97)}
.slot.flash{animation:slotFlash .4s ease}
.ch{transition:all .12s ease;cursor:pointer}.ch:active{transform:scale(0.9)}
.ch.picked{animation:clickFlash .4s ease}
.ch img{transition:all .15s ease}
.ss:active,.bs:active,.rs:active{transform:scale(0.9);transition:transform .05s}
.ss,.bs,.rs{transition:all .15s ease}
.sw{transition:all .2s cubic-bezier(.4,0,.2,1)}.sw:active{transform:scale(0.9)}
.sw::after{transition:all .2s cubic-bezier(.4,0,.2,1)}
.tg{transition:all .12s ease}.tg:active{transform:scale(0.9)}
.srch input{transition:all .2s ease}
.srch input:focus{box-shadow:0 0 12px rgba(10,200,185,.1)}
.mi{transition:all .1s ease}.mi:active{transform:scale(0.97);background:rgba(10,200,185,.12)}
#toast{position:fixed;bottom:16px;left:50%;transform:translateX(-50%) scale(var(--zoom));transform-origin:bottom center;z-index:300;pointer-events:none;display:flex;flex-direction:column;align-items:center;gap:4px}
.toast-msg{padding:8px 20px;border-radius:6px;font-family:'Rajdhani';font-size:13px;font-weight:700;letter-spacing:.5px;animation:toastIn .2s ease;backdrop-filter:blur(8px);white-space:nowrap}
.toast-msg.success{background:rgba(0,255,156,.1);border:1px solid rgba(0,255,156,.3);color:#00FF9C}
.toast-msg.info{background:rgba(10,200,185,.1);border:1px solid rgba(10,200,185,.3);color:#0AC8B9}
.toast-msg.warn{background:rgba(255,78,80,.1);border:1px solid rgba(255,78,80,.3);color:#FF4E50}
.toast-msg.gold{background:rgba(200,170,110,.1);border:1px solid rgba(200,170,110,.3);color:#C8AA6E}
.toast-msg.out{animation:toastOut .2s ease forwards}
</style></head><body>
<div class="app" id="appRoot">
<div class="gp" style="padding:0"><div class="gc tl"></div><div class="gc tr"></div><div class="gc bl"></div><div class="gc br"></div><div class="scanl"></div>
<div class="hdr"><div class="hdr-l"><div class="sub">SESSION · RANKED · v"""+APP_VERSION+r"""</div><h1 class="gshim">HEXTECH DRAFT</h1></div>
<div id="updateBanner" style="display:none;padding:4px 12px;border:1px solid var(--success);border-radius:4px;background:rgba(0,255,156,.06);font-family:JetBrains Mono;font-size:9px;color:var(--success);cursor:pointer;font-weight:600" onclick="doUpdate()">⬆ UPDATE AVAILABLE</div>
<div class="hdr-st"><div class="dot" id="dot"></div><span id="sn">Searching...</span></div>
<div class="zc"><button class="zb" onclick="zO()">−</button><span class="zp" id="zp">100%</span><button class="zb" onclick="zI()">+</button></div>
<button class="gear-btn" onclick="openSettings()">⚙</button>
</div></div>
<div class="m3">
<!-- LEFT -->
<div class="gp tp hs"><div class="gc tl"></div><div class="gc tr"></div><div class="gc bl"></div><div class="gc br"></div>
<div class="sh"><h3>ALLIED TEAM</h3><span class="bd" id="csTimer" style="color:var(--cyan);font-size:11px"></span></div><div id="ts"></div><div class="hdiv"></div>
<div id="liveSection" style="display:none">
<div class="sh"><h3>LIVE PICKS</h3><span class="bd" style="cursor:pointer;color:var(--cyan)" onclick="lookupTeam()">🔍 LOOKUP</span></div>
<div id="livePicks" style="display:flex;gap:3px;flex-wrap:wrap;margin-bottom:4px"></div>
<div class="sh"><h3>ENEMY PICKS</h3></div>
<div id="liveEnemies" style="display:flex;gap:3px;flex-wrap:wrap;margin-bottom:4px"></div>
<div class="sh"><h3>ALL BANS</h3></div>
<div id="liveBans" style="display:flex;gap:3px;flex-wrap:wrap;margin-bottom:4px"></div>
<div class="hdiv"></div>
</div>
<div class="sh"><h3>BAN / BACKUP</h3><span class="bd" id="bc">0/1</span></div>
<div class="brow" id="bsl"></div>
<div class="hdiv"></div><div class="sh"><h3>SPELLS</h3><span class="bd" style="cursor:pointer;color:var(--cyan)" onclick="swapSp()">⇄ SWAP</span></div><div class="srow" id="sr"></div>
<div style="margin-top:4px"><div class="sh"><h3>BACKUP SPELLS</h3><span class="bd" style="cursor:pointer;color:var(--cyan)" onclick="swapBkSp()">⇄ SWAP</span></div></div><div class="srow" id="bsr"></div>
<div style="margin-top:5px"><div class="sh"><h3>RUNES</h3><span class="bd" style="cursor:pointer;color:var(--gold)" onclick="impItems()">📦 ITEMS</span></div></div>
<div class="rs" id="rsl" onclick="openRuneM('rune')">— Select runes</div>
<div id="runePreview"></div>
<div style="margin-top:4px"><div class="sh"><h3>BACKUP RUNE</h3></div></div>
<div class="rs" id="brsl" onclick="openRuneM('backup_rune')">— Backup runes</div>
</div>
<!-- CENTER -->
<div class="gp pp"><div class="gc tl"></div><div class="gc tr"></div><div class="gc bl"></div><div class="gc br"></div>
<div class="pt-top"><h3>CHAMPION POOL</h3><span class="pcnt" id="pcnt">0/0</span>
<button class="lkb ban" onclick="doQB()">✦ BAN</button>
<button class="lkb backup" onclick="doQBk()">✦ BACKUP</button>
<button class="lkb pick" onclick="doQP()">✦ PICK</button>
<button class="lkb pick" onclick="doRandom()" style="border-color:rgba(200,170,110,.3);color:var(--gold)">🎲 FAV</button>
<button class="lkb pick" onclick="doRandomAll()" style="border-color:rgba(10,200,185,.2);color:var(--textm)">🎲 ALL</button></div>
<div style="font-family:JetBrains Mono;font-size:8px;color:var(--textm);padding:0 0 4px;letter-spacing:1px">SHORTCUTS: [P] Pick · [B] Ban · [K] Backup · [R] Random · [ESC] Close · DOUBLE-CLICK to pick</div>
<div id="selInfo" style="display:none;padding:6px 10px;margin-bottom:6px;border:1px solid var(--border);border-radius:6px;background:rgba(1,10,19,.4);align-items:center;gap:8px">
<img id="selImg" style="width:32px;height:32px;border-radius:4px;border:1px solid var(--bordercyan)" src="">
<span id="selName" style="font-size:14px;font-weight:700;letter-spacing:1px;text-transform:uppercase"></span>
<span id="selTags" style="font-size:9px;color:var(--textm);font-family:JetBrains Mono"></span>
<span id="selWR" style="font-size:10px;font-family:JetBrains Mono;font-weight:600;margin-left:4px"></span>
<button class="hb" style="margin-left:auto" onclick="openOpgg()">OP.GG</button>
<button class="hb" onclick="openUgg()">U.GG</button>
<button class="hb" onclick="openCounters()">⚔ COUNTERS</button>
<button class="hb" onclick="editNote()">📝</button>
</div>
<div id="selNote" style="display:none;padding:4px 10px;margin-bottom:6px;font-size:10px;color:var(--gold);font-style:italic;border-left:2px solid var(--gold);margin-left:10px"></div>
<div class="srch"><input id="sb" placeholder="Search champion..." oninput="rG()"></div>
<div class="tgs" id="tb"></div><div class="cg hs" id="cg"></div></div>
<!-- RIGHT -->
<div class="gp rp hs"><div class="gc tl"></div><div class="gc tr"></div><div class="gc bl"></div><div class="gc br"></div>
<div class="prof"><div class="pav" id="pav">?</div><div class="pinf"><div class="pnm" id="pnm">NOT CONNECTED</div><div class="pdt" id="pdt">Waiting for client...</div><div class="pdt" id="prank" style="color:var(--gold)"></div></div></div>
<div id="statsBar" style="display:flex;gap:6px;margin-bottom:8px;flex-wrap:wrap"></div>
<div id="queueBar" style="display:none;padding:5px 8px;margin-bottom:6px;border:1px solid var(--bordercyan);border-radius:4px;background:rgba(10,200,185,.05);font-family:JetBrains Mono;font-size:10px;color:var(--cyan);text-align:center;letter-spacing:2px"></div>
<div class="sh"><h3>PREFERENCES</h3><span class="bd" id="pbdg">0/3 ON</span></div><div class="hdiv"></div><div id="pl"></div><div class="hdiv"></div>
<div class="sh"><h3>MATCH HISTORY</h3><span class="bd" style="cursor:pointer;color:var(--cyan)" onclick="loadHist()">↻</span></div>
<div id="histBox" style="max-height:110px;overflow-y:auto;margin-bottom:4px" class="hs"></div>
<div style="display:flex;gap:4px;margin-bottom:4px">
<button class="hb" style="flex:1;text-align:center;padding:5px 4px" onclick="copyRole()">📋 COPY ROLE</button>
<button class="hb" style="flex:1;text-align:center;padding:5px 4px" onclick="showBans()">🛡 BAN SUGGEST</button>
</div>
<button class="dg" onclick="doD()">⚠ DODGE QUEUE</button></div></div>
<!-- CONSOLE -->
<div class="gp con"><div class="conh"><span class="tl">⟩_ LIVE CONSOLE</span><span class="ct" id="lc">0 ENTRIES</span><span class="lv">STREAMING</span></div>
<div class="conb"><span class="cc" id="cc">● Searching...</span><span class="cp" id="cph"></span><span class="ca" id="caf"></span></div>
<div class="la hs" id="lga"></div></div></div>
<!-- SETTINGS OVERLAY -->
<div class="settings-overlay" id="setOvl">
<div class="gp settings-box">
<div class="gc tl"></div><div class="gc tr"></div><div class="gc bl"></div><div class="gc br"></div>
<div class="sh2"><span>⚙ SETTINGS</span><button onclick="closeSettings()">✕</button></div>
<div class="settings-body hs" id="setBody"></div>
</div>
</div>
<!-- MODAL -->
<div id="toast"></div>
<!-- PICK POPUP -->
<div id="pickPopup" style="display:none;position:fixed;inset:0;background:rgba(1,10,19,.8);backdrop-filter:blur(4px);z-index:250;justify-content:center;align-items:center;transform:scale(var(--zoom));transform-origin:center center">
<div style="background:rgba(9,20,40,.95);border:1px solid var(--bordercyan);border-radius:12px;padding:20px 28px;width:320px;text-align:center;box-shadow:0 0 30px rgba(10,200,185,.15)">
<div style="font-family:Orbitron;font-size:10px;color:var(--textm);letter-spacing:3px;margin-bottom:8px">YOUR TURN TO PICK</div>
<img id="ppImg" style="width:64px;height:64px;border-radius:8px;border:2px solid var(--cyan);margin-bottom:8px" src="">
<div id="ppName" style="font-family:Rajdhani;font-size:18px;font-weight:700;color:var(--text);text-transform:uppercase;letter-spacing:1px;margin-bottom:4px"></div>
<div id="ppTimer" style="font-family:Orbitron;font-size:24px;font-weight:900;color:var(--cyan);margin-bottom:12px;letter-spacing:4px"></div>
<button onclick="pauseAndPickManually()" style="width:100%;padding:10px;font-family:Orbitron;font-size:10px;font-weight:700;letter-spacing:2px;border:1px solid var(--danger);border-radius:6px;color:var(--danger);background:rgba(255,78,80,.06);cursor:pointer;transition:all .15s" onmouseover="this.style.background='rgba(255,78,80,.15)'" onmouseout="this.style.background='rgba(255,78,80,.06)'" onmousedown="this.style.transform='scale(0.95)'" onmouseup="this.style.transform='scale(1)'">⏸ PICK MANUALLY</button>
</div></div>
<div class="mbg" id="mbg"><div class="gp mdl"><div class="gc tl"></div><div class="gc tr"></div><div class="gc bl"></div><div class="gc br"></div>
<div class="mh"><span id="mt">SELECT</span><button onclick="clM()">✕</button></div>
<div class="msr"><input id="ms" placeholder="Search..." oninput="fM()"></div>
<div class="mls hs" id="ml"></div></div></div>
<script>
var cR='TOP',ddV='14.10.1',aT='ALL',sM=null,selC=null,aC=[],aS=[],cMap={},runeMap={},styleMap={},curZoom=100,runeTarget='rune',curRegion='eune';
var RS=['TOP','JUNGLE','MIDDLE','BOTTOM','UTILITY'],RN={TOP:'TOP',JUNGLE:'JNG',MIDDLE:'MID',BOTTOM:'ADC',UTILITY:'SUP'};
var TGS=['ALL','Favorites','Recent','Fighter','Tank','Mage','Assassin','Marksman','Support'];
var PX='data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7';
function cI(i){return i?'https://ddragon.leagueoflegends.com/cdn/'+ddV+'/img/champion/'+i+'.png':'';}
function sI(i){return i?'https://ddragon.leagueoflegends.com/cdn/'+ddV+'/img/spell/'+i+'.png':'';}
function pI(id){var p=runeMap[String(id)];return p?p.icon:'';}
function zI(){curZoom=Math.min(150,curZoom+10);aZ()}
function zO(){curZoom=Math.max(60,curZoom-10);aZ()}
function aZ(){document.documentElement.style.setProperty('--zoom',curZoom/100);document.getElementById('zp').textContent=curZoom+'%'}
async function init(){
try{ddV=await pywebview.api.get_ddragon_ver()}catch(e){}
try{aC=JSON.parse(await pywebview.api.get_champions());aS=JSON.parse(await pywebview.api.get_spells());aC.forEach(function(c){cMap[c.id]=c})}catch(e){}
try{var rd=JSON.parse(await pywebview.api.get_rune_data());if(rd.perks)Object.keys(rd.perks).forEach(function(k){runeMap[k]=rd.perks[k]});if(rd.styles)Object.keys(rd.styles).forEach(function(k){styleMap[k]=rd.styles[k]})}catch(e){}
rTB();rT();rSp();rRn();rP();loadFavs().then(function(){loadRecent().then(function(){rG()})});loadTheme();loadRegion();setInterval(poll,300);
// Auto-check for updates on startup (silent)
setTimeout(async function(){try{
var r=JSON.parse(await pywebview.api.check_update());
if(r.available){pendingUpdateUrl=r.url;
document.getElementById('updateBanner').style.display='block';
document.getElementById('updateBanner').textContent='⬆ UPDATE v'+r.latest+' AVAILABLE — CLICK TO INSTALL'}
}catch(e){}},5000);
// First launch: ask for build source
setTimeout(async function(){try{
var src=await pywebview.api.get_build_source();
if(!src){showSourcePicker()}
}catch(e){}},1500)}

function showSourcePicker(){
var box=document.createElement('div');
box.style.cssText='position:fixed;inset:0;background:rgba(1,10,19,.9);backdrop-filter:blur(8px);z-index:500;display:flex;justify-content:center;align-items:center';
box.innerHTML='<div style="background:rgba(9,20,40,.9);border:1px solid var(--border);border-radius:12px;padding:24px;width:380px;text-align:center;box-shadow:0 16px 50px rgba(0,0,0,.5)">'+
'<div style="font-family:Orbitron;font-size:14px;font-weight:700;color:var(--gold);margin-bottom:4px;letter-spacing:2px">WELCOME TO HEXTECH DRAFT</div>'+
'<div style="font-size:11px;color:var(--textm);margin-bottom:4px">Runes are always fetched from U.GG</div>'+
'<div style="font-size:11px;color:var(--text2);margin-bottom:16px">Choose where to get item builds from. You can change this anytime in Settings.</div>'+
'<div id="srcBtns" style="display:flex;flex-direction:column;gap:8px"></div></div>';
document.body.appendChild(box);
var sources=[
{id:'ugg',name:'U.GG',desc:'Same source as runes · Runes + Items from one page',color:'var(--cyan)'},
{id:'blitz',name:'Blitz.gg',desc:'Popular item builds · Good starter + core data',color:'var(--gold)'},
{id:'lolalytics',name:'Lolalytics',desc:'High sample size stats',color:'var(--success)'}
];
var btns=box.querySelector('#srcBtns');
sources.forEach(function(s){
var b=document.createElement('div');
b.style.cssText='padding:12px 16px;border:1px solid '+s.color+';border-radius:8px;cursor:pointer;transition:all .15s;text-align:left';
b.innerHTML='<div style="font-family:Orbitron;font-size:11px;font-weight:700;color:'+s.color+';letter-spacing:1px">'+s.name+'</div><div style="font-size:10px;color:var(--textm);margin-top:2px">'+s.desc+'</div>';
b.onmouseover=function(){b.style.background='rgba(10,200,185,.08)'};
b.onmouseout=function(){b.style.background='transparent'};
b.onmousedown=function(){b.style.transform='scale(0.97)'};
b.onmouseup=function(){b.style.transform='scale(1)'};
b.onclick=async function(){
try{await pywebview.api.set_global('build_source',s.id)}catch(e){}
box.remove();toast('🛒 Item source: '+s.name,'success')};
btns.appendChild(b)})}
async function loadTheme(){try{var cfg=JSON.parse(await pywebview.api.get_config('TOP'));
if(cfg.light_mode)document.body.classList.add('light');
if(cfg.lite_mode)document.body.classList.add('lite')}catch(e){}}
async function loadRegion(){try{curRegion=await pywebview.api.get_region()}catch(e){curRegion='eune'}}
async function doRandom(){try{var c=JSON.parse(await pywebview.api.random_from_favorites());
if(c){selC=c;asgn('pick',c);toast('🎲 Random: '+c.name,'gold')}else{toast('No favorites yet — click ★ on champions','warn')}}catch(e){}}
function doRandomAll(){
var roleTags={TOP:['Fighter','Tank'],JUNGLE:['Fighter','Assassin','Tank'],MIDDLE:['Mage','Assassin'],BOTTOM:['Marksman','Mage'],UTILITY:['Support','Mage','Tank']};
var tags=roleTags[cR]||['Fighter'];
var pool=aC.filter(function(c){return c.tags&&c.tags.some(function(t){return tags.indexOf(t)>=0})});
if(!pool.length)pool=aC;
var c=pool[Math.floor(Math.random()*pool.length)];
selC=c;asgn('pick',c);toast('🎲 Random: '+c.name,'info')}
async function copyRole(){var from=cR;var to=prompt('Copy '+cR+' config to which role? (TOP/JUNGLE/MIDDLE/BOTTOM/UTILITY)');
if(to&&['TOP','JUNGLE','MIDDLE','BOTTOM','UTILITY'].indexOf(to.toUpperCase())>=0){
try{await pywebview.api.copy_role(from,to.toUpperCase());rT()}catch(e){}}}
async function loadHist(){
var box=document.getElementById('histBox');box.innerHTML='<div style="color:var(--textm);font-size:9px;padding:4px">Loading...</div>';
try{var games=JSON.parse(await pywebview.api.get_match_history());
if(!games||!games.length){box.innerHTML='<div style="color:var(--textm);font-size:9px;padding:4px">No match history</div>';return}
box.innerHTML='';
games.forEach(function(g){
var c=cMap[g.champId];var img=c?cI(c.img):'';var name=c?c.name:'?';
var kda=g.kills+'/'+g.deaths+'/'+g.assists;
var min=Math.floor(g.duration/60);
var row=document.createElement('div');
row.style.cssText='display:flex;align-items:center;gap:6px;padding:3px 6px;border-radius:4px;margin-bottom:2px;background:'+(g.win?'rgba(0,255,156,.06)':'rgba(255,78,80,.06)')+';border-left:2px solid '+(g.win?'var(--success)':'var(--danger)');
row.innerHTML=(img?'<img src="'+img+'" style="width:24px;height:24px;border-radius:3px">':'')+
'<span style="font-size:10px;font-weight:600;color:var(--text);width:55px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'+name+'</span>'+
'<span style="font-size:10px;font-family:JetBrains Mono;color:'+(g.win?'var(--success)':'var(--danger)')+'">'+kda+'</span>'+
'<span style="font-size:8px;color:var(--textm);margin-left:auto">'+min+'m</span>';
box.appendChild(row)})}catch(e){box.innerHTML='<div style="color:var(--textm);font-size:9px;padding:4px">Not connected</div>'}}
async function lookupTeam(){try{
var names=JSON.parse(await pywebview.api.lookup_team());
if(names.length){
var q=names.join(',');
window.open('https://www.op.gg/multisearch/'+curRegion+'?summoners='+encodeURIComponent(q),'_blank')}
else{alert('Not in champ select or no teammates found')}}catch(e){}}
async function showBans(){
var box=document.getElementById('histBox');box.innerHTML='<div style="color:var(--textm);font-size:9px;padding:4px">Fetching ban suggestions for '+cR+'...</div>';
try{var bans=JSON.parse(await pywebview.api.get_ban_suggestions(cR));
if(!bans||!bans.length){box.innerHTML='<div style="color:var(--textm);font-size:9px;padding:4px">No ban data available</div>';return}
box.innerHTML='';
bans.forEach(function(b){
var row=document.createElement('div');
row.style.cssText='display:flex;align-items:center;gap:6px;padding:3px 6px;border-radius:4px;margin-bottom:2px;background:rgba(255,78,80,.04);border-left:2px solid var(--danger);cursor:pointer';
row.innerHTML='<img src="'+cI(b.img)+'" style="width:24px;height:24px;border-radius:3px">'+
'<span style="font-size:10px;font-weight:600;color:var(--text)">'+b.name+'</span>'+
'<span style="font-size:9px;font-family:JetBrains Mono;color:var(--danger);margin-left:auto">'+(b.banRate*100).toFixed(1)+'% ban</span>';
row.onclick=function(){selC=b;asgn('ban',b)};
box.appendChild(row)})}catch(e){box.innerHTML='<div style="color:var(--textm);font-size:9px;padding:4px">Failed to fetch</div>'}}
function rTB(){var c=document.getElementById('tb');c.innerHTML='';TGS.forEach(function(t){var d=document.createElement('div');d.className='tg'+(t===aT?' on':'');d.textContent=t;d.onclick=function(){aT=t;rTB();rG()};c.appendChild(d)})}
function rG(){var q=document.getElementById('sb').value.toLowerCase(),g=document.getElementById('cg');g.innerHTML='';
var f=aC.filter(function(c){return c.name.toLowerCase().indexOf(q)>=0});
if(aT==='Favorites')f=f.filter(function(c){return favsList.indexOf(c.id)>=0});
else if(aT==='Recent')f=f.filter(function(c){return recentList.indexOf(c.id)>=0});
else if(aT!=='ALL')f=f.filter(function(c){return c.tags&&c.tags.indexOf(aT)>=0});
document.getElementById('pcnt').textContent=f.length+' / '+aC.length;
if(!f.length){g.innerHTML='<div class="nr">'+(aT==='Favorites'?'NO FAVORITES YET — CLICK ★ ON CHAMPIONS':'NO CHAMPIONS FOUND')+'</div>';return}
f.forEach(function(c){var d=document.createElement('div');d.className='ch';d.setAttribute('data-id',c.id);
var isFav=favsList.indexOf(c.id)>=0;
if(isFav)d.style.cssText='border:2px solid var(--gold);background:rgba(200,170,110,.06);border-radius:6px';
d.innerHTML='<div style="position:relative"><img src="'+cI(c.img)+'" onerror="this.style.opacity=0.1"'+(isFav?' style="border-color:var(--gold)"':'')+'>'+
'<div id="fav_'+c.id+'" style="position:absolute;top:-4px;right:-4px;width:20px;height:20px;border-radius:50%;cursor:pointer;font-size:13px;display:flex;align-items:center;justify-content:center;'+
(isFav?'background:var(--gold);color:var(--bg);text-shadow:none':'background:rgba(1,10,19,.7);color:rgba(200,170,110,.3);text-shadow:0 0 4px rgba(0,0,0,.8)')+
'" onmousedown="event.stopPropagation()" onclick="event.stopPropagation();togFav('+c.id+')">'+(isFav?'★':'☆')+'</div>'+
'</div><div class="cn"'+(isFav?' style="color:var(--gold)"':'')+'>'+c.name+'</div>';
d.onclick=function(){champClick(c,d)};g.appendChild(d)})}
function selChamp(c){selC=c;if(sM){asgn(sM,c);sM=null;rT();return}
document.querySelectorAll('.ch').forEach(function(el){el.classList.toggle('sel',el.getAttribute('data-id')==String(c.id))});
var si=document.getElementById('selInfo');si.style.display='flex';
document.getElementById('selImg').src=cI(c.img);
document.getElementById('selName').textContent=c.name;
document.getElementById('selTags').textContent=(c.tags||[]).join(' · ');
document.getElementById('selWR').textContent='';
pywebview.api.get_champ_winrate(String(c.id)).then(function(r){try{
var d=JSON.parse(r);if(d){var col=d.rate>=50?'var(--success)':'var(--danger)';
document.getElementById('selWR').innerHTML='<span style="color:'+col+'">'+d.rate+'% WR</span> <span style="color:var(--textm)">('+d.total+'g)</span>'}
}catch(e){}});
document.getElementById('selNote').style.display='none';
pywebview.api.get_champ_note(String(c.id)).then(function(n){
if(n){document.getElementById('selNote').textContent='📝 '+n;document.getElementById('selNote').style.display='block'}
})}
/* DOUBLE-CLICK: assign to current mode (pick/ban/backup) */
var lastClick={id:0,time:0};
function champClick(c,el){
var now=Date.now();
if(lastClick.id===c.id&&(now-lastClick.time)<350){
el.classList.add('picked');selC=c;
var mode=sM||'pick';
asgn(mode,c);sM=null;rT();return}
lastClick={id:c.id,time:now};selChamp(c)}
/* TOAST SYSTEM */
function toast(msg,type){type=type||'info';
var box=document.getElementById('toast');
var el=document.createElement('div');el.className='toast-msg '+type;el.textContent=msg;
box.appendChild(el);
setTimeout(function(){el.classList.add('out');setTimeout(function(){el.remove()},200)},2000)}
async function editNote(){if(!selC)return;
var cur=await pywebview.api.get_champ_note(String(selC.id));
var n=prompt('Note for '+selC.name+':',cur||'');
if(n!==null){await pywebview.api.set_champ_note(String(selC.id),n);
if(n){document.getElementById('selNote').textContent='📝 '+n;document.getElementById('selNote').style.display='block'}
else{document.getElementById('selNote').style.display='none'}}}
function openOpgg(){if(!selC)return;window.open('https://www.op.gg/champions/'+selC.img.toLowerCase(),'_blank')}
function openUgg(){if(!selC)return;window.open('https://u.gg/lol/champions/'+selC.img.toLowerCase()+'/build','_blank')}
function openCounters(){if(!selC)return;window.open('https://u.gg/lol/champions/'+selC.img.toLowerCase()+'/matchups','_blank')}
/* KEYBOARD SHORTCUTS */
document.addEventListener('keydown',function(e){
if(e.target.tagName==='INPUT')return;
if(e.key==='p'||e.key==='P'){if(selC)doQP()}
if(e.key==='b'||e.key==='B'){if(selC)doQB()}
if(e.key==='k'||e.key==='K'){if(selC)doQBk()}
if(e.key==='r'||e.key==='R'){doRandom()}
if(e.key==='Escape'){clM();document.getElementById('setOvl').classList.remove('show')}
})
async function swapSp(){try{await pywebview.api.swap_spells(cR);toast('⇄ Spells swapped','info')}catch(e){}rSp()}
async function swapBkSp(){try{await pywebview.api.swap_backup_spells(cR);toast('⇄ Backup spells swapped','info')}catch(e){}rSp()}
async function impItems(){try{var ok=await pywebview.api.import_items_now(cR);
toast(ok?'📦 Items imported!':'📦 No items found','ok'?'success':'warn')}catch(e){}}
async function togFav(champId){try{var favs=JSON.parse(await pywebview.api.toggle_favorite(String(champId)));
favsList=favs;var c=cMap[champId];var isFav=favs.indexOf(champId)>=0;
toast(isFav?'★ '+((c&&c.name)||'Champion')+' favorited':'☆ '+((c&&c.name)||'Champion')+' unfavorited',isFav?'gold':'info');
rG()}catch(e){}}
var favsList=[];var recentList=[];
async function loadFavs(){try{favsList=JSON.parse(await pywebview.api.get_favorites())}catch(e){favsList=[]}}
async function loadRecent(){try{recentList=JSON.parse(await pywebview.api.get_recently_played())}catch(e){recentList=[]}}async function asgn(mode,c){try{
await pywebview.api.set_setting(cR,mode+'_id',String(c.id));
await pywebview.api.set_setting(cR,mode+'_name',c.name);
await pywebview.api.set_setting(cR,mode+'_img',c.img);
var labels={pick:'⚔ Picked',ban:'⊘ Banned',backup:'🔄 Backup'};
toast((labels[mode]||mode)+' '+c.name,mode==='ban'?'warn':mode==='backup'?'gold':'success');
}catch(e){}rT();rG()}
function doQP(){if(selC)asgn('pick',selC)}
function doQB(){if(selC)asgn('ban',selC)}
function doQBk(){if(selC)asgn('backup',selC)}
async function clr(mode,role){var r=role||cR;try{
await pywebview.api.set_setting(r,mode+'_id','__null__');
await pywebview.api.set_setting(r,mode+'_name','None');
await pywebview.api.set_setting(r,mode+'_img','__null__');
if(mode==='pick'){await pywebview.api.set_setting(r,'rune_data','__null__');await pywebview.api.set_setting(r,'rune_id','__null__');await pywebview.api.set_setting(r,'rune_name','None')}
if(mode==='backup'){await pywebview.api.set_setting(r,'backup_rune_data','__null__');await pywebview.api.set_setting(r,'backup_rune_id','__null__');await pywebview.api.set_setting(r,'backup_rune_name','None');
await pywebview.api.set_setting(r,'backup_spell1_id','__null__');await pywebview.api.set_setting(r,'backup_spell1_name','None');await pywebview.api.set_setting(r,'backup_spell1_img','__null__');
await pywebview.api.set_setting(r,'backup_spell2_id','__null__');await pywebview.api.set_setting(r,'backup_spell2_name','None');await pywebview.api.set_setting(r,'backup_spell2_img','__null__')}
}catch(e){}selC=null;toast('✕ Cleared '+mode,'info');rT();rSp();rRn();rG()}
async function rT(){try{
var allCfgs={};
for(var ri=0;ri<RS.length;ri++){allCfgs[RS[ri]]=JSON.parse(await pywebview.api.get_config(RS[ri]))}
var cfg=allCfgs[cR];
var ts=document.getElementById('ts');ts.innerHTML='';
RS.forEach(function(r){var isU=(r===cR);var rCfg=allCfgs[r];
var s=document.createElement('div');s.className='slot'+(isU?' on':'');
var pImg=rCfg.pick_img?cI(rCfg.pick_img):'';var pNm=rCfg.pick_name||'None';
s.innerHTML='<img class="pt '+(pImg?'':'emp')+'" src="'+(pImg||PX)+'"><div class="si"><div class="rl">'+RN[r]+(isU?' <span class="you">♛ YOU</span>':'')+'</div><div class="nm '+(pNm==='None'||pNm==='—'?'emp':'')+'">'+(pNm==='None'?'—':pNm)+'</div></div>'+(pImg?'<div style="cursor:pointer;color:var(--textm);font-size:11px;padding:2px 4px;border-radius:3px" onmouseover="this.style.color=\'var(--danger)\'" onmouseout="this.style.color=\'var(--textm)\'" onclick="event.stopPropagation();clr(\'pick\',\''+r+'\')">✕</div>':'');
s.onclick=function(){if(cR!==r){cR=r;rT();rSp();rRn();document.getElementById('selInfo').style.display='none';document.getElementById('selNote').style.display='none'}};ts.appendChild(s)});
var bs=document.getElementById('bsl');bs.innerHTML='';
// Ban slot with cancel
var bImg=cfg.ban_img?cI(cfg.ban_img):'';
var bWrap=document.createElement('div');bWrap.style.cssText='position:relative;display:inline-block';
var be=document.createElement('div');be.className='bs'+(sM==='ban'?' on':'');
be.innerHTML=(bImg?'<img src="'+bImg+'">':'')+'<div class="bs-label">BAN</div>';
be.onclick=function(){sM=sM==='ban'?null:'ban';rT()};bWrap.appendChild(be);
if(bImg){var bx=document.createElement('div');bx.style.cssText='position:absolute;top:-4px;right:-4px;width:16px;height:16px;border-radius:50%;background:rgba(255,78,80,.8);color:#fff;font-size:10px;cursor:pointer;display:flex;align-items:center;justify-content:center;z-index:2;font-weight:700';bx.textContent='✕';bx.onclick=function(e){e.stopPropagation();clr('ban')};bWrap.appendChild(bx)}
bs.appendChild(bWrap);
// Backup slot with cancel
var bkImg=cfg.backup_img?cI(cfg.backup_img):'';
var bkWrap=document.createElement('div');bkWrap.style.cssText='position:relative;display:inline-block';
var bke=document.createElement('div');bke.className='bs'+(sM==='backup'?' on':'');bke.style.borderColor='rgba(200,170,110,.3)';
bke.innerHTML=(bkImg?'<img src="'+bkImg+'">':'')+'<div class="bs-label" style="color:var(--gold)">BACKUP</div>';
bke.onclick=function(){sM=sM==='backup'?null:'backup';rT()};bkWrap.appendChild(bke);
if(bkImg){var bkx=document.createElement('div');bkx.style.cssText='position:absolute;top:-4px;right:-4px;width:16px;height:16px;border-radius:50%;background:rgba(255,78,80,.8);color:#fff;font-size:10px;cursor:pointer;display:flex;align-items:center;justify-content:center;z-index:2;font-weight:700';bkx.textContent='✕';bkx.onclick=function(e){e.stopPropagation();clr('backup')};bkWrap.appendChild(bkx)}
bs.appendChild(bkWrap);
document.getElementById('bc').textContent=(cfg.ban_name&&cfg.ban_name!=='None'?'1':'0')+'/1'}catch(e){}}
async function rSp(){try{var cfg=JSON.parse(await pywebview.api.get_config(cR));
var r=document.getElementById('sr');r.innerHTML='';
[[cfg.spell1_img,'spell1',1],[cfg.spell2_img,'spell2',2]].forEach(function(x){
var url=x[0]?sI(x[0]):'';var el=document.createElement('div');el.className='ss';
el.innerHTML=url?'<img src="'+url+'">':'';el.onclick=function(){openSpM(x[2],'main')};r.appendChild(el)});
// Backup spells
var br=document.getElementById('bsr');br.innerHTML='';
[[cfg.backup_spell1_img,'backup_spell1',1],[cfg.backup_spell2_img,'backup_spell2',2]].forEach(function(x){
var url=x[0]?sI(x[0]):'';var el=document.createElement('div');el.className='ss';
el.style.borderColor='rgba(200,170,110,.3)';
el.innerHTML=url?'<img src="'+url+'">':'';el.onclick=function(){openSpM(x[2],'backup')};br.appendChild(el)})
}catch(e){}}
async function rRn(){try{var cfg=JSON.parse(await pywebview.api.get_config(cR));
document.getElementById('rsl').textContent=cfg.rune_name&&cfg.rune_name!=='None'?'📜 '+cfg.rune_name:'— Select runes';
document.getElementById('brsl').textContent=cfg.backup_rune_name&&cfg.backup_rune_name!=='None'?'📜 '+cfg.backup_rune_name:'— Backup runes';
var preview=document.getElementById('runePreview');preview.innerHTML='';
var rd=cfg.rune_data;
if(rd&&rd.selectedPerkIds&&rd.selectedPerkIds.length>0){
var box=document.createElement('div');box.className='rune-display';
var perks=document.createElement('div');perks.className='rune-perks';
rd.selectedPerkIds.forEach(function(pid,idx){
var pk=document.createElement('div');pk.className='rune-perk'+(idx===0?' ks':'');
var icon=pI(pid);if(icon)pk.innerHTML='<img src="'+icon+'" title="'+(runeMap[String(pid)]?runeMap[String(pid)].name:'')+'">';
perks.appendChild(pk)});box.appendChild(perks);preview.appendChild(box)}}catch(e){}}
var mI=[],mCb=null;
function openSpM(slot,spellType){document.getElementById('mt').textContent=(spellType==='backup'?'BACKUP ':'')+' SPELL '+slot;document.getElementById('ms').value='';
mI=aS.map(function(s){return{id:s.id,name:s.name,img:s.img,isSpell:true}});
var prefix=spellType==='backup'?'backup_spell':'spell';
mCb=async function(item){try{
await pywebview.api.set_setting(cR,prefix+slot+'_id',String(item.id));
await pywebview.api.set_setting(cR,prefix+slot+'_name',item.name);
await pywebview.api.set_setting(cR,prefix+slot+'_img',item.img)}catch(e){}rSp()};
document.getElementById('mbg').classList.add('show');fM();setTimeout(function(){document.getElementById('ms').focus()},100)}
async function openRuneM(target){runeTarget=target;var items=[];try{items=JSON.parse(await pywebview.api.get_rune_pages(target,cR))}catch(e){}
document.getElementById('mt').textContent=target==='backup_rune'?'BACKUP RUNE PAGE':'RUNE PAGE';document.getElementById('ms').value='';mI=items;
mCb=async function(item){try{
var idK=runeTarget+'_id',nmK=runeTarget+'_name',dataK=runeTarget+'_data';
if(item.source==='recommended'&&item.data){
await pywebview.api.set_setting(cR,idK,'__null__');await pywebview.api.set_setting(cR,nmK,item.name);
await pywebview.api.set_setting(cR,dataK,JSON.stringify(item.data))}
else{await pywebview.api.set_setting(cR,idK,String(item.id));await pywebview.api.set_setting(cR,nmK,item.name);
await pywebview.api.set_setting(cR,dataK,'__null__')}}catch(e){}rRn()};
document.getElementById('mbg').classList.add('show');fM()}
function clM(){document.getElementById('mbg').classList.remove('show')}
function fM(){var q=document.getElementById('ms').value.toLowerCase(),list=document.getElementById('ml');list.innerHTML='';
mI.filter(function(i){return i.name.toLowerCase().indexOf(q)>=0}).forEach(function(item){
var d=document.createElement('div');d.className='mi';
var iu=item.isSpell?sI(item.img):'';
var perkHtml='';
if(item.data&&item.data.selectedPerkIds&&item.data.selectedPerkIds.length>0){
perkHtml='<div class="rpv">';
item.data.selectedPerkIds.slice(0,6).forEach(function(pid,idx){
var icon=pI(pid);if(icon)perkHtml+='<img src="'+icon+'" class="'+(idx===0?'ks':'')+'">';});
perkHtml+='</div>'}
d.innerHTML=(iu?'<img src="'+iu+'">':'')+
'<span class="mn">'+item.name+'</span>'+perkHtml+
(item.source?'<span class="src">'+(item.source==='recommended'?'⭐ OP.GG':'📄 MY PAGE')+'</span>':'');
d.onclick=function(){clM();if(mCb)mCb(item);toast('📜 '+item.name,'success')};list.appendChild(d)})}
function rP(){var ps=[
{key:'auto_accept',nm:'Auto-Accept Queue',ds:'Accept ready check automatically',icon:'⚡'},
{key:'auto_ban',nm:'Auto-Ban',ds:'Lock ban champion automatically',icon:'⊘'},
{key:'auto_pick',nm:'Auto-Pick',ds:'Lock pick automatically. OFF = popup to pick manually',icon:'⚔'},
{key:'auto_spells',nm:'Auto-Spells',ds:'OFF = keep your spells. ON = set from config or role defaults',icon:'🔥'},
{key:'auto_runes',nm:'Auto-Runes',ds:'OFF = keep your runes. ON = auto-import if no rune is set',icon:'📜'},
{key:'auto_items',nm:'Auto-Items',ds:'OFF by default. ON = import item build to shop after lock',icon:'🛒'},
{key:'sound_alert',nm:'Sound Alert',ds:'Beep on match found + 5s timer warning',icon:'🔔'},
{key:'chat_on',nm:'Auto-Chat',ds:'Send message in champ select',icon:'💬',btn:'EDIT',ba:'eC'},
{key:'afk_on',nm:'Anti-AFK',ds:'Press Y + right-click center when idle in-game',icon:'🖱',btn:'TIMER',ba:'eA'}];
var c=document.getElementById('pl');c.innerHTML='';
ps.forEach(function(p){var row=document.createElement('div');row.className='pr';
var ex=p.btn?'<button class="hb" onclick="'+p.ba+'()">'+p.btn+'</button>':'';
row.innerHTML='<div class="pi"><div class="pn">'+p.icon+' '+p.nm+'</div><div class="pd">'+p.ds+'</div></div>'+ex+'<div class="sw" id="sw_'+p.key+'" onclick="tS(\''+p.key+'\')"></div>';
c.appendChild(row)});lS()}
async function lS(){try{var cfg=JSON.parse(await pywebview.api.get_config('TOP'));
['auto_accept','auto_ban','auto_pick','auto_spells','auto_runes','auto_items','sound_alert','chat_on','afk_on'].forEach(function(k){var el=document.getElementById('sw_'+k);if(el)el.classList.toggle('on',!!cfg[k])});uPB()}catch(e){}}
async function tS(k){var el=document.getElementById('sw_'+k);var on=!el.classList.contains('on');el.classList.toggle('on',on);
try{await pywebview.api.set_global(k,on)}catch(e){}uPB();
var names={auto_accept:'Auto-Accept',auto_ban:'Auto-Ban',auto_pick:'Auto-Pick',auto_spells:'Auto-Spells',auto_runes:'Auto-Runes',auto_items:'Auto-Items',sound_alert:'Sound Alert',chat_on:'Auto-Chat',afk_on:'Anti-AFK'};
toast((names[k]||k)+': '+(on?'ON':'OFF'),on?'success':'info')}
function uPB(){var on=0;var total=0;document.querySelectorAll('.sw').forEach(function(t){total++;if(t.classList.contains('on'))on++});
document.getElementById('pbdg').textContent=on+'/'+total+' ON'}
async function eC(){var m=prompt('Chat message:','GLHF');if(m)try{await pywebview.api.set_global('chat_msg',m)}catch(e){}}
async function eA(){var v=prompt('Idle seconds (5-120):','30');if(v)try{await pywebview.api.set_global('afk_threshold',v)}catch(e){}}
async function doD(){if(confirm('Dodge? You will lose LP.')){try{await pywebview.api.dodge();toast('⚠ Dodged queue','warn')}catch(e){}}}
async function togglePause(){try{await pywebview.api.toggle_pause_pick()}catch(e){}}
async function pauseAndPickManually(){
try{await pywebview.api.toggle_pause_pick();
window._pickPopupDismissed=true;
document.getElementById('pickPopup').style.display='none';
toast('⏸ Auto-pick PAUSED — pick manually in client','warn')}catch(e){}}
function openSettings(){
var c=document.getElementById('setBody');c.innerHTML='';
var cats=[
{title:'APPEARANCE',items:[
{key:'light_mode',nm:'Light Mode',ds:'Light color scheme for daytime use'},
{key:'lite_mode',nm:'Lite Mode',ds:'Disable blur, animations & shadows for performance'},
{key:'auto_minimize',nm:'Auto-Minimize',ds:'Minimize window when game starts'}
]},
{title:'REGION',items:[
{key:'_region',nm:'Server Region',ds:'Used for op.gg, Porofessor, team lookup links',action:'changeRegion'}
]},
{title:'BUILD SOURCE',items:[
{key:'_source',nm:'Item Build Source',ds:'Runes always from U.GG. Items from your chosen source',action:'changeBuildSource'}
]},
{title:'LOCK-IN BEHAVIOR',items:[
{key:'auto_spells',nm:'Auto-Spells',ds:'Set summoner spells after locking pick'},
{key:'auto_runes',nm:'Auto-Runes',ds:'Import rune page after locking pick'},
{key:'auto_items',nm:'Auto-Items',ds:'Import item build from op.gg after locking pick'}
]},
{title:'ALERTS',items:[
{key:'sound_alert',nm:'Sound Alert',ds:'Beep when match found + timer warning at 5s'}
]},
{title:'DATA',items:[
{key:'_update',nm:'Check for Updates',ds:'Check GitHub for a newer version',action:'checkUpdate'},
{key:'_export',nm:'Export Config',ds:'Copy all settings to clipboard for sharing',action:'expCfg'},
{key:'_import',nm:'Import Config',ds:'Paste settings from clipboard',action:'impCfg'},
{key:'_reset',nm:'Reset All Settings',ds:'Factory reset — delete all config',action:'rstCfg'},
{key:'_opgg',nm:'Open op.gg Profile',ds:'View your summoner profile on op.gg',action:'openMyOpgg'},
{key:'_prof',nm:'Porofessor Multi-Search',ds:'Look up all teammates on Porofessor',action:'openPoro'},
{key:'_clearall',nm:'Clear All Roles',ds:'Remove all pick/ban/backup from every role',action:'clearAllRoles'},
{key:'_clear',nm:'Clear Console Log',ds:'Clear all log entries',action:'clearLog'}
]}
];
cats.forEach(function(cat){
var h=document.createElement('div');h.className='scat';h.textContent=cat.title;c.appendChild(h);
cat.items.forEach(function(item){
var row=document.createElement('div');row.className='srow';
if(item.action){
row.innerHTML='<div class="si2"><div class="sn">'+item.nm+'</div><div class="sd">'+item.ds+'</div></div><button class="hb" onclick="'+item.action+'()">GO</button>';
}else{
row.innerHTML='<div class="si2"><div class="sn">'+item.nm+'</div><div class="sd">'+item.ds+'</div></div><div class="sw" id="set_'+item.key+'" onclick="togSet(\''+item.key+'\')"></div>';
}
c.appendChild(row)})});
document.getElementById('setOvl').classList.add('show');
loadSetStates()}
function closeSettings(){document.getElementById('setOvl').classList.remove('show')}
async function loadSetStates(){try{
var cfg=JSON.parse(await pywebview.api.get_config('TOP'));
['light_mode','lite_mode','auto_minimize','auto_spells','auto_runes','auto_items','sound_alert'].forEach(function(k){
var el=document.getElementById('set_'+k);if(el)el.classList.toggle('on',!!cfg[k])})}catch(e){}}
async function togSet(k){
var el=document.getElementById('set_'+k);var on=!el.classList.contains('on');el.classList.toggle('on',on);
try{await pywebview.api.set_global(k,on)}catch(e){}
if(k==='light_mode'){document.body.classList.toggle('light',on);toast(on?'☀ Light Mode':'🌙 Dark Mode','info')}
if(k==='lite_mode'){document.body.classList.toggle('lite',on);toast(on?'⚡ Lite Mode ON':'✨ Effects ON','info')}}
async function expCfg(){try{var d=await pywebview.api.export_config();
if(navigator.clipboard){await navigator.clipboard.writeText(d);alert('Config copied to clipboard!')}
else{prompt('Copy this:',d)}}catch(e){alert('Export failed')}}
async function impCfg(){var d=prompt('Paste config JSON:');if(d){try{
var ok=await pywebview.api.import_config(d);
if(ok){alert('Config imported! Reloading...');location.reload()}
else{alert('Invalid config')}}catch(e){alert('Import failed')}}}
async function rstCfg(){if(confirm('Reset ALL settings to defaults? This cannot be undone.')){
try{await pywebview.api.reset_config();alert('Config reset! Reloading...');location.reload()}catch(e){}}}
async function openMyOpgg(){try{var s=JSON.parse(await pywebview.api.get_status());
if(s.summoner)window.open('https://www.op.gg/summoners/'+curRegion+'/'+encodeURIComponent(s.summoner),'_blank');
else alert('Not connected yet')}catch(e){}}
async function openPoro(){try{var names=JSON.parse(await pywebview.api.lookup_team());
if(names.length){window.open('https://porofessor.gg/pregame/'+curRegion+'/'+encodeURIComponent(names[0]),'_blank')}
else{var s=JSON.parse(await pywebview.api.get_status());
if(s.summoner)window.open('https://porofessor.gg/pregame/'+curRegion+'/'+encodeURIComponent(s.summoner),'_blank');
else alert('Not connected')}}catch(e){}}
async function clearAllRoles(){if(!confirm('Clear ALL picks/bans/backups from every role?'))return;
var roles=['TOP','JUNGLE','MIDDLE','BOTTOM','UTILITY'];
var keys=['pick','ban','backup'];
for(var ri=0;ri<roles.length;ri++){for(var ki=0;ki<keys.length;ki++){
try{await pywebview.api.set_setting(roles[ri],keys[ki]+'_id','__null__');
await pywebview.api.set_setting(roles[ri],keys[ki]+'_name','None');
await pywebview.api.set_setting(roles[ri],keys[ki]+'_img','__null__')}catch(e){}}}
rT();rSp();rRn();rG()}
function clearLog(){document.getElementById('lga').innerHTML='<div class="ll"><span class="ts">['+new Date().toTimeString().slice(0,8)+']</span><span class="ok">Console cleared</span></div>'}
async function changeRegion(){
var regions=['euw','eune','na','kr','jp','oce','br','las','lan','tr','ru','sg','ph','tw','th','vn'];
var cur=curRegion;
var r=prompt('Current: '+cur.toUpperCase()+'\\n\\nAvailable regions:\\n'+regions.map(function(x){return x.toUpperCase()}).join(', ')+'\\n\\nType your region:');
if(r){r=r.toLowerCase().trim();
if(regions.indexOf(r)>=0){curRegion=r;
try{await pywebview.api.set_global('region',r)}catch(e){}
toast('🌍 Region: '+r.toUpperCase(),'success')}
else{toast('Unknown region: '+r,'warn')}}}
async function changeBuildSource(){
var cur=await pywebview.api.get_build_source();
var r=prompt('Current item source: '+(cur||'not set').toUpperCase()+'\\nRunes are always from U.GG\\n\\nAvailable item sources:\\nUGG — Same as runes, all from one page\\nBLITZ — Popular item builds\\nLOLALYTICS — High sample stats\\n\\nType source name:');
if(r){r=r.toLowerCase().trim();
if(['ugg','blitz','lolalytics'].indexOf(r)>=0){
try{await pywebview.api.set_global('build_source',r)}catch(e){}
toast('🛒 Item source: '+r.toUpperCase(),'success')}
else{toast('Unknown source. Use: ugg, blitz, or lolalytics','warn')}}}
var pendingUpdateUrl=null;
async function checkUpdate(){try{
var r=JSON.parse(await pywebview.api.check_update());
if(r.available){
pendingUpdateUrl=r.url;
document.getElementById('updateBanner').style.display='block';
document.getElementById('updateBanner').textContent='⬆ UPDATE v'+r.latest+' AVAILABLE'+(r.url?' — CLICK TO INSTALL':' — visit GitHub');
alert('Update available!\\n\\nCurrent: v'+r.current+'\\nLatest: v'+r.latest+'\\n\\n'+(r.notes||'')+'\\n\\n'+(r.url?'Click the green banner to install.':'Visit: '+r.html_url))
}else{alert('You are on the latest version (v'+r.current+')')}}catch(e){alert('Update check failed — check your internet connection')}}
async function doUpdate(){if(!pendingUpdateUrl){window.open('https://github.com/jimman0I/League-Auto-Accept-Enhanced-Menu','_blank');return}
if(!confirm('Download and install update? The app will restart.'))return;
try{document.getElementById('updateBanner').textContent='⬆ DOWNLOADING UPDATE...';
var r=JSON.parse(await pywebview.api.do_update(pendingUpdateUrl));
if(!r.success){alert('Download failed — try downloading manually from GitHub')}}catch(e){alert('Update failed: '+e)}}

async function poll(){try{var s=JSON.parse(await pywebview.api.get_status());
document.getElementById('dot').className='dot'+(s.connected?' on':'');
document.getElementById('sn').textContent=s.connected?s.summoner:'Searching...';
document.getElementById('sn').style.color=s.connected?'var(--text)':'var(--textm)';
if(s.connected){document.getElementById('pav').textContent=s.summoner.charAt(0).toUpperCase();
document.getElementById('pnm').textContent=s.summoner.toUpperCase();
document.getElementById('pdt').textContent='Lvl '+s.level+' · Phase: '+s.phase+(s.role&&s.phase==='ChampSelect'?' · '+s.role:'');
document.getElementById('prank').textContent=s.rank?(s.rank+' · '+s.lp+' LP'+(s.wr?' · '+s.wr+' WR':'')):''}
// Stats bar
var sb=document.getElementById('statsBar');
if(s.connected&&s.stats){
var st=s.stats;
sb.innerHTML='<span style="color:var(--cyan);background:rgba(10,200,185,.08);padding:4px 12px;border-radius:6px;border:1px solid rgba(10,200,185,.2);font-size:11px;font-weight:600">⚡ '+st.accepts+' Accepts</span>'+
'<span style="color:var(--danger);background:rgba(255,78,80,.06);padding:4px 12px;border-radius:6px;border:1px solid rgba(255,78,80,.15);font-size:11px;font-weight:600">⊘ '+st.bans+' Bans</span>'+
'<span style="color:var(--gold);background:rgba(200,170,110,.06);padding:4px 12px;border-radius:6px;border:1px solid rgba(200,170,110,.15);font-size:11px;font-weight:600">⚔ '+st.picks+' Picks</span>'+
'<span style="color:var(--success);background:rgba(0,255,156,.06);padding:4px 12px;border-radius:6px;border:1px solid rgba(0,255,156,.15);font-size:11px;font-weight:600">🎮 '+st.games+' Games</span>'}
else{sb.innerHTML=''}
// Queue timer
var qb=document.getElementById('queueBar');
if(s.queue_time>0){qb.style.display='block';var qm=Math.floor(s.queue_time/60);var qs=s.queue_time%60;
qb.textContent='IN QUEUE '+String(qm).padStart(2,'0')+':'+String(qs).padStart(2,'0')}
else{qb.style.display='none'}
// Phase display in console only
document.getElementById('cc').textContent=s.connected?'● '+s.summoner:'● Searching...';
document.getElementById('cc').style.color=s.connected?'var(--cyan)':'var(--textm)';
// Countdown timer
var ctEl=document.getElementById('csTimer');
if(s.phase==='ChampSelect'&&s.time_left>0){
ctEl.textContent=String(Math.floor(s.time_left/60)).padStart(2,'0')+':'+String(s.time_left%60).padStart(2,'0');
ctEl.style.color=s.time_left<=5?'var(--danger)':'var(--cyan)'}
else{ctEl.textContent=''}
// Live champ select tracker
var liveEl=document.getElementById('liveSection');
if(s.phase==='ChampSelect'){
liveEl.style.display='block';
var lp=document.getElementById('livePicks');lp.innerHTML='';
(s.allies||[]).forEach(function(a){
var c=cMap[a.champId];var img=c?cI(c.img):'';
var el=document.createElement('div');
el.style.cssText='width:32px;height:32px;border-radius:4px;border:2px solid '+(a.isMe?'var(--cyan)':'var(--border)')+';background:var(--bg);overflow:hidden';
if(img)el.innerHTML='<img src="'+img+'" style="width:100%;height:100%">';
el.title=(c?c.name:'?')+' — '+(a.position||'?');
lp.appendChild(el)});
var le=document.getElementById('liveEnemies');le.innerHTML='';
(s.enemies||[]).forEach(function(a){
var c=cMap[a.champId];var img=c?cI(c.img):'';
var el=document.createElement('div');
el.style.cssText='width:32px;height:32px;border-radius:4px;border:2px solid var(--danger);background:var(--bg);overflow:hidden;opacity:'+(a.champId?'1':'0.2');
if(img)el.innerHTML='<img src="'+img+'" style="width:100%;height:100%">';
el.title=c?c.name:'Unknown';
le.appendChild(el)});
var lb=document.getElementById('liveBans');lb.innerHTML='';
(s.bans||[]).forEach(function(bid){
var c=cMap[bid];var img=c?cI(c.img):'';
var el=document.createElement('div');
el.style.cssText='width:24px;height:24px;border-radius:3px;border:1px solid rgba(255,78,80,.3);background:var(--bg);overflow:hidden;opacity:0.5;filter:grayscale(1)';
if(img)el.innerHTML='<img src="'+img+'" style="width:100%;height:100%">';
el.title=c?c.name:'?';
lb.appendChild(el)})
}else{liveEl.style.display='none'}
// Pick popup — shows when it's your turn to pick with auto-pick ON
var pp=document.getElementById('pickPopup');
if(s.phase==='ChampSelect'&&s.time_left>0&&!s.pause_pick){
var tp=s.timer_phase||'';
var isPick=tp.indexOf('PICK')>=0||tp==='FINALIZATION';
if(isPick&&!window._pickPopupDismissed){
// Get current pick champion from config
try{var pcfg=JSON.parse(await pywebview.api.get_config(cR));
if(pcfg.pick_name&&pcfg.pick_name!=='None'&&pcfg.auto_pick){
pp.style.display='flex';
document.getElementById('ppImg').src=pcfg.pick_img?cI(pcfg.pick_img):'';
document.getElementById('ppName').textContent=pcfg.pick_name;
document.getElementById('ppTimer').textContent=String(Math.floor(s.time_left/60)).padStart(2,'0')+':'+String(s.time_left%60).padStart(2,'0');
document.getElementById('ppTimer').style.color=s.time_left<=5?'var(--danger)':'var(--cyan)';
}else{pp.style.display='none'}}catch(e){}
}else{pp.style.display='none'}
}else{pp.style.display='none';window._pickPopupDismissed=false}
document.getElementById('cph').textContent=s.connected?'Phase: '+s.phase:'';
document.getElementById('caf').textContent='AFK: '+s.afk;
document.getElementById('lc').textContent=s.logs.length+' ENTRIES';
var la=document.getElementById('lga');
la.innerHTML=s.logs.map(function(l){return '<div class="ll"><span class="ts">['+l.time+']</span><span class="'+(l.type==='success'?'ok':(l.type==='debug'?'db':'nf'))+'">'+l.msg+'</span></div>'}).join('');
la.scrollTop=la.scrollHeight;
if(s.phase==='ChampSelect'&&s.role&&s.role!==cR){cR=s.role;rT();rSp();rRn()}
// Auto-minimize when game starts
if(s.phase==='InProgress'&&!window._minimized){
try{var cfg2=JSON.parse(await pywebview.api.get_config('TOP'));
if(cfg2.auto_minimize){window._minimized=true;pywebview.api.minimize_window()}}catch(e){}}
if(s.phase!=='InProgress'){window._minimized=false}
}catch(e){}}
function waitForApi(){if(window.pywebview&&window.pywebview.api)init();else setTimeout(waitForApi,100)}
document.addEventListener('DOMContentLoaded',waitForApi);
</script></body></html>"""

def main():
    import webview
    api=Api()
    window=webview.create_window('Hextech Draft',html=HTML,js_api=api,width=1200,height=820,resizable=True,background_color='#010A13')
    webview.start()

if __name__=='__main__':
    main()
