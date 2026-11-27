"""Smoothed chart lines stay within the data and keep its peaks (run in Node)."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

APP_JS = Path(__file__).resolve().parent / "static" / "app.js"
NODE = shutil.which("node")

CHECKS = r"""
const flat = Array.from({ length: 400 }, (_, i) => ({ x: i, y: 50 + Math.sin(i / 9) * 5 }));
flat[200] = { x: 200, y: 5 };    // a one-day spike (up on screen)
flat[310] = { x: 310, y: 95 };   // a one-day dip
const kept = downsampleLargestTriangle(flat, 60);

// Every cubic piece's control points lie between its two end points, so the curve
// (inside their convex hull) never goes past a value the data has.
function withinBands(points) {
  const d = monotoneCurve(points);
  const pieces = [...d.matchAll(/C([-\d.]+),([-\d.]+) ([-\d.]+),([-\d.]+) ([-\d.]+),([-\d.]+)/g)];
  return pieces.every((match, i) => {
    const low = Math.min(points[i].y, points[i + 1].y) - 0.01, high = Math.max(points[i].y, points[i + 1].y) + 0.01;
    return [Number(match[2]), Number(match[4])].every(y => y >= low && y <= high);
  }) && pieces.length === points.length - 1;
}
const jagged = [{ x: 0, y: 10 }, { x: 1, y: 80 }, { x: 2, y: 20 }, { x: 3, y: 21 }, { x: 4, y: 90 }, { x: 5, y: 0 }];
const gapped = linePath([{ x: 0, y: 1 }, { x: 1, y: 2 }, null, { x: 3, y: 4 }, { x: 4, y: 5 }], true);
console.log(JSON.stringify({
  keptCount: kept.length,
  keepsEnds: kept[0] === flat[0] && kept[kept.length - 1] === flat[399],
  keepsSpike: kept.includes(flat[200]),
  keepsDip: kept.includes(flat[310]),
  bandsJagged: withinBands(jagged),
  bandsSampled: withinBands(kept),
  segments: (gapped.match(/M/g) || []).length,
  straightWhenOff: linePath(jagged, false).includes("C") === false,
  shortStaysStraight: linePath([{ x: 0, y: 0 }, { x: 1, y: 1 }], true) === "M0.00,0.00L1.00,1.00",
}));
"""


@unittest.skipIf(NODE is None, "node is not installed")
class ChartLinesTest(unittest.TestCase):
    def test_smoothing_keeps_the_data_honest(self) -> None:
        source = APP_JS.read_text(encoding="utf-8")
        block = re.search(r"/\* chart-lines:start.*?chart-lines:end \*/", source, re.DOTALL)
        self.assertIsNotNone(block, "chart line helpers not found in app.js")
        result = subprocess.run([NODE, "-e", block.group(0) + CHECKS], capture_output=True, text=True, timeout=30, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        checks = json.loads(result.stdout)
        self.assertEqual(checks.pop("keptCount"), 60)
        self.assertEqual(checks.pop("segments"), 2)
        self.assertEqual(checks, dict.fromkeys(checks, True))


if __name__ == "__main__":
    unittest.main()
