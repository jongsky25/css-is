"""Transient, layout-anchored DTRAK subject reading. No file writes or logs."""
import base64
import csv
import io
import re
import subprocess
import time

import numpy as np
from PIL import Image, ImageOps


def _ocr(image, deadline, config='tsv'):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise subprocess.TimeoutExpired('tesseract', 8)
    with io.BytesIO() as output:
        image.save(output, 'PNG')
        result = subprocess.run(['tesseract', 'stdin', 'stdout', '-l', 'eng', '--psm', '6',
                                 '-c', 'debug_file=/dev/null'] + ([config] if config else []),
                                input=output.getvalue(), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                timeout=min(4, remaining), check=True)
    return result.stdout.decode('utf-8', errors='replace')


def _words(tsv):
    return [dict(text=r['text'], x=int(r['left']), y=int(r['top']), w=int(r['width']), h=int(r['height']))
            for r in csv.DictReader(io.StringIO(tsv), delimiter='\t', quoting=csv.QUOTE_NONE)
            if r.get('level') == '5' and r.get('text', '').strip()]


def read_subject(png, page_text):
    if not (re.search(r'DTRAK|Document Tracking Information System', page_text, re.I)
            and re.search(r'ORIGINATING OFFICE|ROUTING SLIP', page_text, re.I)):
        return None
    result = {'status': 'region_not_found', 'method': 'dtrak_subject_cell', 'value': '', 'raw': '',
              'reason': 'The DTRAK subject box could not be located. Check the page preview.'}
    deadline = time.monotonic() + 8
    try:
        with Image.open(io.BytesIO(png)) as source:
            image = source.convert('L')
        image.thumbnail((1800, 2400))
        # Estimate small scan skew from horizontal grid-line strength, not text.
        small = image.copy(); small.thumbnail((600, 850))
        best, best_score = 0, 0
        for angle in (-2, -1.5, -1, -.5, 0, .5, 1, 1.5, 2):
            probe = small.rotate(angle, fillcolor=255)
            pixels = np.asarray(probe) < 150
            score = float(np.sort(pixels.mean(axis=1))[-12:].sum())
            if score > best_score: best, best_score = angle, score
            probe.close()
        small.close()
        aligned = image.rotate(best, resample=Image.Resampling.BICUBIC, fillcolor=255); image.close()
        image = aligned
        try:
            words = _words(_ocr(image, deadline))
            anchors = [w for w in words if re.fullmatch(r'[|I1\[!]*SUBJECT[:;|]?', w['text'], re.I)]
            pixels = np.asarray(image) < 160
            if not anchors:
                # If OCR loses SUBJECT entirely, use the standard TYPE OF DOCUMENT
                # row followed by the next full-width cell, bounded by grid lines.
                types = [w for w in words if w['text'].strip('|:').upper() == 'TYPE']
                for kind in types:
                    same = [w for w in words if abs(w['y']-kind['y']) < max(w['h'], kind['h'])]
                    if not any(w['text'].strip('|:').upper() == 'DOCUMENT' for w in same): continue
                    density = pixels[:, max(0, kind['x']-20):int(image.width*.95)].mean(axis=1)
                    rows = np.where(density > .6)[0]
                    rows = rows[(rows > kind['y']+kind['h']) & (rows < kind['y']+image.height*.15)]
                    if len(rows):
                        anchors.append(dict(x=kind['x'], y=int(rows[0])+kind['h']+5, h=kind['h']))
            if len(anchors) != 1: return result
            anchor = anchors[0]
            x, y, h = anchor['x'], anchor['y'], anchor['h']
            # A subject cell spans most of the page; locate its actual horizontal borders.
            row_density = pixels[:, max(0, x-20):int(image.width*.95)].mean(axis=1)
            lines = np.where(row_density > .6)[0]
            above = lines[(lines < y) & (lines > y-image.height*.12)]
            below = lines[(lines > y+h) & (lines < y+image.height*.18)]
            if not len(above) or not len(below): return result
            top, bottom = int(above[-1]), int(below[0])
            if bottom-top < h*1.5: return result
            columns = pixels[top+3:bottom-3].mean(axis=0)
            borders = np.where(columns > .65)[0]
            lefts, rights = borders[borders < x], borders[borders > x+image.width*.5]
            if not len(lefts) or not len(rights): return result
            left, right = int(lefts[-1]), int(rights[0])
            pad = max(3, round(image.width/400))
            crop = image.crop((left+pad, top+pad, right-pad, bottom-pad))
            try:
                result['box'] = [left/image.width, top/image.height, right/image.width, bottom/image.height]
                preview = crop.copy(); preview.thumbnail((650, 220))
                with io.BytesIO() as output:
                    preview.save(output, 'JPEG', quality=75)
                    result['preview'] = 'data:image/jpeg;base64,' + base64.b64encode(output.getvalue()).decode()
                preview.close()
                # Upscale only this small cell; white padding separates text from crop edges.
                scale = min(2, 2400/crop.width)
                enlarged = crop.resize((int(crop.width*scale), int(crop.height*scale)), Image.Resampling.LANCZOS)
                padded = ImageOps.expand(enlarged, border=16, fill=255); enlarged.close()
                try: raw = _ocr(padded, deadline, '').strip()
                finally: padded.close()
                result['raw'] = raw[:1500]
                value = re.sub(r'^[|I1\[!]*SUBJECT\s*[:;|]?\s*', '', raw, flags=re.I)
                value = re.sub(r'\s+', ' ', value).strip()
                if len(re.sub(r'[^A-Za-z]', '', value)) < 4:
                    result.update(status='empty', reason='The subject box was located but OCR found no text.')
                elif len(value) > 500 or re.search(r'REQUIRED/ACTION|TAKEN/\s*REMARKS', value, re.I):
                    result.update(status='rejected', reason='The subject reading needs review; it may include text outside the subject box.')
                else:
                    result.update(status='read', value=value, reason='Read from the DTRAK subject box; verify against the preview.')
                return result
            finally: crop.close()
        finally: image.close()
    except (ValueError, KeyError, OSError, subprocess.SubprocessError):
        result.update(status='failed', reason='The subject-box reading did not finish. Retry or enter the subject manually.')
        return result
