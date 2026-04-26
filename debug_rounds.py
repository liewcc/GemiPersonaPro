with open('engine.log', encoding='utf-8', errors='replace') as f, open('out_121.txt', 'w', encoding='utf-8') as out:
    for line in f:
        if '"round": 121' in line or '"round": 99' in line or '"round": 1' in line:
            out.write(line)
