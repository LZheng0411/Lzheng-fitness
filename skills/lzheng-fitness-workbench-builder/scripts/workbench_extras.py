"""Independent knowledge projection: editable content is not the UI shell."""
import json,re
KNOWLEDGE=re.compile(r'(<script id="knowledge-library-data" type="application/json">)([\s\S]*?)(</script>)')

def preserve(old,new):
    matches=list(KNOWLEDGE.finditer(old))
    if len(matches)>1:raise ValueError('Duplicate knowledge data blocks')
    if not matches:return new
    json.loads(matches[0][2])
    if len(KNOWLEDGE.findall(new))!=1:raise ValueError('Target template lacks knowledge support')
    return KNOWLEDGE.sub(lambda m:m[1]+matches[0][2]+m[3],new)
