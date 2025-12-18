# inspect_debug_html.py
import re, sys, os, json

fn = "debug_quotation_preview.html"
if len(sys.argv) > 1:
    fn = sys.argv[1]

if not os.path.exists(fn):
    print("No existe el archivo:", fn)
    sys.exit(1)

txt = open(fn, "r", encoding="utf-8").read()

# Buscar scripts que contengan la palabra payload o INJECT_JSON_PLACEHOLDER
scripts = re.findall(r"(<script[^>]*>)(.*?)(</script>)", txt, flags=re.DOTALL | re.IGNORECASE)
found = False
for i,(open_tag, body, close_tag) in enumerate(scripts):
    if "payload" in body or "INJECT_JSON_PLACEHOLDER" in body or "QUOTATION" in body[:200]:
        found = True
        print("---- Script block #{} ----".format(i))
        head = body.strip()[:1000]
        # Mostrar primeras 1000 chars y también buscar 'var payload'
        idx = body.find("var payload")
        if idx >= 0:
            start = max(0, idx-120)
            end = min(len(body), idx+400)
            print("Contexto alrededor de 'var payload':\n")
            print(body[start:end])
        else:
            # si no hay var payload, mostrar el principio
            print("Script preview:\n")
            print(head)
        # print a little more for debugging
        print("\n--- End of block ---\n")
# Si no lo encontramos, también busca la inserción directa del JSON
if not found:
    m = re.search(r"/\* INJECT_JSON_PLACEHOLDER \*/", txt)
    if m:
        print("Encontrado explicit placeholder /* INJECT_JSON_PLACEHOLDER */ en el HTML (pos {})".format(m.start()))
    else:
        # dump first script block
        if scripts:
            print("No se detectó payload; mostrando el primer script (por si acaso):")
            print(scripts[0][1][:1200])
        else:
            print("No hay bloques <script> en el HTML o no contiene payload.")