import sys, io, json, os, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

os.chdir('F:/Locator/MopedMap')

import importlib.util
spec = importlib.util.spec_from_file_location('mopedmap', 'F:/Locator/MopedMap/mopedmap.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

# Test the user's example
text = 'ОТБОЙ ОПАСНОСТИ АТАКИ БПЛА в Белгородском, Валуйском, Краснояружском, Борисовском, Грайворонском, Ивнянском, Ракитянском, Корочанском, Яковлевском, Прохоровском, Чернянском МО, Губкинском и Старооскольском ГО'

print("Input:", text[:80] + "...")
print()
locs = mod.extract_locations(text)
print("Results:")
for l in locs:
    print("  %-25s -> %-20s (%s) [%.4f, %.4f] type=%s" % (
        l.get('matched','?'), l['name'], l.get('subject','?'),
        l['lat'], l['lon'], l.get('type','?')))
