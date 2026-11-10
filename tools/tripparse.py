import json,re,html,sys
MO={'janv':1,'févr':2,'fév':2,'mars':3,'avr':4,'mai':5,'juin':6,'juil':7,'août':8,'sept':9,'oct':10,'nov':11,'déc':12}
def text(d):
    t=d.get('plaintextBody') or ''
    if not t:
        h=d.get('htmlBody',''); h=re.sub(r'<(script|style)[^>]*>.*?</\1>','',h,flags=re.S); t=re.sub(r'<[^>]+>','\n',h); t=html.unescape(t)
    return [l.strip() for l in t.split('\n') if l.strip()]
def fdate(s):
    m=re.match(r'(\d+)\s+([^\s.]+)\.?\s+(\d{4})',s.strip()); d,mo,y=m.groups(); return f"{y}-{MO[mo[:4]] if mo[:4] in MO else MO[mo[:3]]:02d}-{int(d):02d}"
def parse(d):
    L=text(d); subj=d.get('subject','')
    code=re.search(r'#(\d{10,})#',subj).group(1)
    out={'code':code,'booked_at':d.get('date')}
    if 'annulation' in subj.lower() or 'cancellation' in subj.lower():
        out['kind']='cancel'
        i=L.index('Hôtel'); out['hotel']=L[i+1]
        i=L.index('Nom du voyageur'); out['guest']=L[i+1]
        i=L.index('Période de séjour'); per=L[i+1]
    else:
        out['kind']='new'
        i=L.index('Confirmation d\'établissement nº'); out['hotel']=L[i+2] if L[i+1]=='/' else L[i+1]
        i=L.index('Nom du voyageur:'); out['guest']=L[i+1]
        i=L.index('Période de séjour:'); per=L[i+1]
        try:
            i=L.index('Voyageurs (estimés):'); out['guests']=int(re.search(r'(\d+)',L[i+1]).group(1))
        except Exception: pass
        try:
            i=L.index('Votre paiement'); out['total']=float(L[i+2].replace(',','.'))
        except Exception: pass
        try:
            i=L.index('Frais de nettoyage'); out['cleaning']=float(L[i+1].replace('+','').replace(',','.'))
        except Exception: out['cleaning']=0
        if 'total' in out: out['stay']=round(out['total']-out.get('cleaning',0),2)
    a,b=per.split('|')[0].split(' - '); out['checkin']=fdate(a); out['checkout']=fdate(b)
    g=out['guest'].replace(',',' ')
    if '/' in g: last,first=g.split('/',1); g=first+' '+last
    out['guest']=' '.join(x.capitalize() for x in re.split(r'\s+',g.strip()) if x)
    return out
if __name__=='__main__':
    for f in sys.argv[1:]:
        print(json.dumps(parse(json.load(open(f))),ensure_ascii=False))
