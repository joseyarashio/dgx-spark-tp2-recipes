import sys,json,re,urllib.request
def get(u): return json.load(urllib.request.urlopen(u,timeout=30))
def clean(h): return re.sub(r"\s+"," ",re.sub(r"<[^>]+>"," ",h)).strip()
tid=sys.argv[1]; n=int(sys.argv[2]); maxc=int(sys.argv[3])
d=get(f"https://forums.developer.nvidia.com/t/{tid}.json")
ids=d["post_stream"]["stream"][-n:]
q="&".join(f"post_ids[]={i}" for i in ids)
pp=get(f"https://forums.developer.nvidia.com/t/{tid}/posts.json?{q}")["post_stream"]["posts"]
for p in pp:
    print(f"#{p['post_number']} {p['created_at'][:16]} {p['username']}: {clean(p['cooked'])[:maxc]}\n")
