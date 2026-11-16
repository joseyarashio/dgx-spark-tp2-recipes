import sys,json,re,urllib.request
for tid in sys.argv[1:]:
    d=json.load(urllib.request.urlopen(f"https://forums.developer.nvidia.com/t/{tid}.json",timeout=30))
    print(f"=== #{tid} {d.get('title')} posts={d.get('posts_count')}")
    for p in d.get("post_stream",{}).get("posts",[])[:10]:
        t=re.sub(r"<[^>]+>"," ",p.get("cooked","")); t=re.sub(r"\s+"," ",t).strip()
        print(f"  #{p.get('post_number')} {p.get('created_at','')[:16]} {p.get('username')}: {t[:700]}")
