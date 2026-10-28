#!/usr/bin/env python3
"""Outil unique du portail propriétaire Aurora Conciergerie.

Variables d'environnement attendues (jamais écrites dans le dépôt) :
  LODGIFY_KEY   clé API Lodgify
  DATA_KEY      clé hexadécimale (32 octets) qui chiffre les fichiers data/*.enc
  AURORA_PIN    code d'accès du propriétaire (chiffre la page publiée)

Commandes :
  python tools/portail.py recaps list   <bien>              liste les récaps enregistrés
  python tools/portail.py recaps add    <bien> '<json>'     ajoute un récap (objet ou liste), dédoublonné par code
  python tools/portail.py recaps import <bien> <fichier>    importe un fichier JSON de récaps (remplace)
  python tools/portail.py build                              télécharge Lodgify, reconstruit les pages
"""
import json, os, sys, base64, hashlib, datetime, subprocess
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG=json.load(open(os.path.join(ROOT,'tools','config.json')))
SRC={"AirbnbIntegration":"Airbnb","BookingCom":"Booking.com","BookingComIntegration":"Booking.com","Manual":"Direct","OwnerWebsite":"Direct","Expedia":"Expedia","VrboIntegration":"Vrbo"}

def env(name):
    v=os.environ.get(name)
    if not v: sys.exit(f"variable {name} manquante")
    return v

# ---------- fichiers chiffrés (données propriétaires, dépôt public) ----------
def _k(): return bytes.fromhex(env('DATA_KEY'))
def enc_write(path,obj):
    iv=os.urandom(12); ct=AESGCM(_k()).encrypt(iv,json.dumps(obj,ensure_ascii=False).encode(),None)
    open(os.path.join(ROOT,path),'w').write(json.dumps({"iv":base64.b64encode(iv).decode(),"data":base64.b64encode(ct).decode()}))
def enc_read(path,default=None):
    p=os.path.join(ROOT,path)
    if not os.path.exists(p): return default
    d=json.load(open(p)); return json.loads(AESGCM(_k()).decrypt(base64.b64decode(d['iv']),base64.b64decode(d['data']),None))

def prop(pid):
    for o in CFG['owners']:
        for p in o['properties']:
            if p['id']==pid: return p
    sys.exit(f"bien inconnu : {pid}")

# ---------- récaps (versement propriétaire par séjour) ----------
def recaps_cmd(args):
    sub,pid=args[0],args[1]; p=prop(pid); rows=enc_read(p['recaps'],[])
    if sub=='list':
        for r in sorted(rows,key=lambda r:r['checkin']): print(r['checkin'],r['checkout'],r.get('confirmation_code'),r['guest_name'],r['owner_payout'])
        print(len(rows),"récaps, total",round(sum(r['owner_payout'] or 0 for r in rows),2),"€")
    elif sub=='add':
        new=json.loads(args[2]); new=new if isinstance(new,list) else [new]
        codes={r.get('confirmation_code') for r in rows}; added=0
        for n in new:
            for f in ('guest_name','checkin','checkout','owner_payout'):
                if f not in n: sys.exit(f"champ manquant : {f}")
            if n.get('confirmation_code') and n['confirmation_code'] in codes: print("déjà présent :",n['confirmation_code']); continue
            if any(r['checkin']==n['checkin'] and r['guest_name']==n['guest_name'] for r in rows): print("déjà présent :",n['guest_name'],n['checkin']); continue
            rows.append(n); added+=1
        enc_write(p['recaps'],rows); print(added,"récap(s) ajouté(s),",len(rows),"au total")
    elif sub=='import':
        rows=json.load(open(args[2])); enc_write(p['recaps'],rows); print(len(rows),"récaps importés")
    else: sys.exit("sous-commande inconnue")

# ---------- Lodgify ----------
def lodgify_all():
    K=env('LODGIFY_KEY'); allb=[]; page=1
    while True:
        url=f"https://api.lodgify.com/v2/reservations/bookings?stayFilter=All&includeExternal=true&includeTransactions=false&page={page}&size=100"
        out=subprocess.run(['curl','-s','--max-time','60','-H',f'X-ApiKey: {K}',url],capture_output=True,text=True).stdout
        d=json.loads(out); items=d.get('items',[])
        if not items: break
        allb+=items; page+=1
        if page>400: break
    return allb

def lodgify_rows(allb,pid_lodgify):
    rows=[]
    for x in allb:
        if x['property_id']!=pid_lodgify or x.get('is_deleted'): continue
        code=None
        try: code=json.loads(x.get('source_text') or '{}').get('confirmationCode')
        except Exception: pass
        rows.append({"checkin":x['arrival'],"checkout":x['departure'],"status":x['status'],
            "guest":(x.get('guest') or {}).get('name') or "Voyageur","platform":SRC.get(x.get('source'),x.get('source') or "Direct"),
            "stay":(x.get('subtotals') or {}).get('stay'),"total":x.get('total_amount'),
            "guests":(x['rooms'][0].get('people') if x.get('rooms') else None),"code":code,"booked_at":x.get('created_at')})
    rows.sort(key=lambda r:r['checkin']); return rows

# ---------- construction ----------
def build_property(cfg,lg_rows):
    lg=[r for r in lg_rows if r["status"]=="Booked" and r["checkout"]>cfg["since"]]
    recaps=enc_read(cfg['recaps'],[])
    bycode={r.get("confirmation_code"):r for r in recaps if r.get("confirmation_code")}
    byci={r["checkin"]:r for r in recaps}
    ical=[];stays=[]
    for r in lg:
        n=(datetime.date.fromisoformat(r["checkout"])-datetime.date.fromisoformat(r["checkin"])).days
        ical.append({"start":r["checkin"],"end":r["checkout"],"guest":r["guest"],"platform":r["platform"],"guests":r["guests"],"code":r["code"],"stay":r.get("stay"),"total":r.get("total"),"booked_at":r.get("booked_at")})
        rc=bycode.get(r["code"]) or byci.get(r["checkin"])
        if rc:
            stays.append({"guest":r["guest"],"checkin":r["checkin"],"checkout":r["checkout"],"nights":n,
                "code":r["code"] or rc.get("confirmation_code") or f"{r['checkin']}-{r['guest']}",
                "guests":r["guests"] or rc.get("num_guests"),"guest_paid":rc.get("guest_total_paid") or r.get("total"),
                "owner_payout":rc.get("owner_payout") or 0,"aurora_payout":rc.get("aurora_payout"),
                "host_gross":r.get("stay"),"platform":r["platform"],"pdf":rc.get("pdf_url")})
    known={s["code"] for s in stays}|{s["checkin"] for s in stays}
    for rc in recaps:
        if rc.get("confirmation_code") in known or rc["checkin"] in known: continue
        n=rc.get("nights") or (datetime.date.fromisoformat(rc["checkout"])-datetime.date.fromisoformat(rc["checkin"])).days
        stays.append({"guest":rc["guest_name"],"checkin":rc["checkin"],"checkout":rc["checkout"],"nights":n,"code":rc.get("confirmation_code") or rc["checkin"],
            "guests":rc.get("num_guests"),"guest_paid":rc.get("guest_total_paid"),"owner_payout":rc.get("owner_payout") or 0,
            "aurora_payout":rc.get("aurora_payout"),"host_gross":None,"platform":"Airbnb","pdf":rc.get("pdf_url")})
    stays.sort(key=lambda s:s["checkout"])
    market=None; mp=os.path.join(ROOT,cfg.get('market') or '')
    if cfg.get('market') and os.path.exists(mp): market=json.load(open(mp))
    return {k:cfg[k] for k in ("id","name","short","address","platforms","since","adr")}|{"ical":ical,"stays":stays,"market":market}

def build_cmd():
    pin=env('AURORA_PIN'); allb=lodgify_all(); print(len(allb),"réservations Lodgify lues")
    tpl=open(os.path.join(ROOT,'tools','template.html')).read()
    for o in CFG['owners']:
        props=[build_property(p,lodgify_rows(allb,p['lodgify_property_id'])) for p in o['properties']]
        data={"owner":o['greeting'],"updated":datetime.date.today().isoformat(),"properties":props}
        salt=os.urandom(16); iv=os.urandom(12); ITER=250000
        key=hashlib.pbkdf2_hmac('sha256',pin.encode(),salt,ITER,dklen=32)
        ct=AESGCM(key).encrypt(iv,json.dumps(data,ensure_ascii=False).encode(),None)
        enc={"salt":base64.b64encode(salt).decode(),"iv":base64.b64encode(iv).decode(),"iter":ITER,"data":base64.b64encode(ct).decode()}
        open(os.path.join(ROOT,o['output']),'w').write(tpl.replace('__DATA__',json.dumps(enc)))
        for p in props: print(o['slug'],"/",p['id'],":",len(p['ical']),"réservations,",len(p['stays']),"séjours récapitulés, versements",round(sum(s['owner_payout'] for s in p['stays']),2),"€")

if __name__=='__main__':
    a=sys.argv[1:]
    if not a: sys.exit(__doc__)
    if a[0]=='recaps': recaps_cmd(a[1:])
    elif a[0]=='build': build_cmd()
    else: sys.exit(__doc__)
