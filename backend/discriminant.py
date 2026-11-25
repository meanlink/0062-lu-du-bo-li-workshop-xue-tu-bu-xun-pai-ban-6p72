from statistics import mean

FEATURES=("setup","handoff","teardown")

def classify(anchors, target):
    groups={}
    for row in anchors:
        groups.setdefault(row["label"],[]).append(row)
    if set(groups) != {"bench","handoff","ready"} or min(map(len,groups.values())) < 2:
        raise ValueError("每种导师标签至少需要两份独立课堂评分")
    centers={label:{f:mean(r[f] for r in rows) for f in FEATURES} for label,rows in groups.items()}
    variance={f:max(0.25,sum((r[f]-centers[r["label"]][f])**2 for r in anchors)/(len(anchors)-len(groups))) for f in FEATURES}
    contributions={label:{f:round((target[f]-center[f])**2/variance[f],4) for f in FEATURES} for label,center in centers.items()}
    order=sorted((sum(scores.values()),label) for label,scores in contributions.items())
    return {
        "discipline":order[0][1],
        "margin":round(order[1][0]-order[0][0],4),
        "drivers":contributions,
        "n_distinct":len(anchors)
    }
