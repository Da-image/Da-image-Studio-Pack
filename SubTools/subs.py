import os
import sys
import argparse
import xml.etree.ElementTree as ET
import difflib
import re
import copy
import urllib.parse

import subprocess

try:
    from pypinyin import lazy_pinyin
    HAS_PINYIN = True
except ImportError:
    HAS_PINYIN = False

# --- Fuzzy Matching Constants (from match_duel 2.py v48) ---
V48_NUM_MAP = {"0":"零","1":"一","2":"二","3":"三","4":"四","5":"五","6":"六","7":"七","8":"八","9":"九"}
V48_HIGH_CONFIDENCE = 0.75
V48_SEARCH_WINDOW = 30

def clean_text_v48(text):
    if not text: return ""
    text = str(text).lower()
    for k, v in V48_NUM_MAP.items(): text = text.replace(k, v)
    return "".join(re.findall(r'[\u4e00-\u9fa5a-z]+', text))

def get_similarity_v48(seg, clip_text):
    s_c = clean_text_v48(seg)
    c_c = clean_text_v48(clip_text)
    if not s_c or not c_c: return 0.0

    len_ratio = len(s_c) / len(c_c) if len(c_c) > 0 else 0
    is_length_mismatch = (len_ratio <= 0.5 or len_ratio >= 2.0)
    max_possible_score = 1.0
    len_s = len(s_c)
    len_c = len(c_c)
    if len_s >= 5 or len_c >= 5:
        diff = abs(len_s - len_c)
        if diff > 2:
            max_possible_score = 0.55

    base_score = 0.0

    if len(s_c) >= 2 and s_c in c_c:
        ratio = len(s_c) / len(c_c)
        len_diff = len(c_c) - len(s_c)
        if len(s_c) >= 5 and len_diff > 2:
            ratio = 0.49
        base_score = 0.2 + 0.8 * ratio
        if ratio <= 0.5:
            base_score = min(base_score, 0.60)
        if len(s_c) >= 12 and ratio > 0.5:
            base_score = max(base_score, 0.90)
        base_score = min(1.0, base_score)
    elif len(c_c) >= 2 and c_c in s_c:
        ratio = len(c_c) / len(s_c)
        len_diff = len(s_c) - len(c_c)
        if len(c_c) >= 5 and len_diff > 2:
            ratio = 0.49
        if ratio <= 0.5:
            base_score = 0.4 + 0.4 * ratio
        else:
            base_score = 0.6 + 0.4 * ratio
            base_score = max(base_score, 0.92)
        if ratio < 0.4:
            base_score = min(base_score, 0.60)
    else:
        if is_length_mismatch:
            base_score = 0.4
        else:
            raw_score = difflib.SequenceMatcher(None, s_c, c_c).ratio()
            len_diff_val = len(c_c) - len(s_c)
            if len(s_c) >= 5 and len_diff_val > 2:
                 raw_score = min(raw_score, 0.55)
            elif len(c_c) >= 5 and (-len_diff_val) > 2:
                 raw_score = min(raw_score, 0.55)
            len_ratio = len(s_c) / len(c_c) if len(c_c) > 0 else 0
            if len(s_c) < 2 or len(c_c) < 2:
                if s_c != c_c:
                    base_score = 0.0
                else:
                    base_score = 1.0
            else:
                common_prefix = 0
                min_len = min(len(s_c), len(c_c))
                for i in range(min_len):
                    if s_c[i] == c_c[i]: common_prefix += 1
                    else: break
                if len_ratio > 0.8 and len_ratio < 1.2 and raw_score > 0.6 and raw_score < 0.8:
                    base_score = raw_score - 0.1
                elif len_ratio <= 0.5 and raw_score > 0.6:
                    base_score = min(raw_score, 0.60)
                else:
                    base_score = raw_score

    if base_score < V48_HIGH_CONFIDENCE and HAS_PINYIN:
        if is_length_mismatch and base_score < 0.5:
             pass
        else:
             s_py, c_py = "".join(lazy_pinyin(s_c)), "".join(lazy_pinyin(c_c))
             if s_py in c_py:
                 ratio = len(s_c) / len(c_c) if len(c_c) > 0 else 0
                 if ratio <= 0.5:
                     py_score = 0.60
                 else:
                     py_score = 0.85
             else:
                 py_score = difflib.SequenceMatcher(None, s_py, c_py).ratio() * 0.8
             base_score = max(base_score, py_score)

    final_score = min(base_score, max_possible_score)
    return min(1.0, final_score)

def find_best_match_v48(seg, pool, last_idx, used_indices=None, window=V48_SEARCH_WINDOW):
    if not pool: return {"score": 0.0, "it": None, "idx": 0}
    if used_indices is None: used_indices = set()
    n = len(pool)
    curr_start = max(0, min(last_idx, n-1))
    curr_end = min(n, curr_start + window)
    local_indices = list(range(curr_start, curr_end))
    global_indices = list(range(0, curr_start)) + list(range(curr_end, n))
    best = {"score": -1.0, "it": None, "idx": curr_start}
    for i in local_indices:
        if i in used_indices: continue
        item = pool[i]
        score = get_similarity_v48(seg, item["text"])
        if score > best["score"]:
            best = {"score": score, "it": item, "idx": i}
        if best["score"] >= V48_HIGH_CONFIDENCE:
            return best
    if best["score"] < V48_HIGH_CONFIDENCE:
        for i in global_indices:
            if i in used_indices: continue
            item = pool[i]
            score = get_similarity_v48(seg, item["text"])
            if score > best["score"]:
                best = {"score": score, "it": item, "idx": i}
            if best["score"] >= 0.98:
                return best
    return best

# --- SRT Parsing Logic ---
def parse_srt_time(t_str):
    """Parse SRT timecode 'HH:MM:SS,mmm' to total seconds (float)."""
    try:
        t_str = t_str.strip().replace(',', '.')
        h, m, s = t_str.split(':')
        return int(h) * 3600 + int(m) * 60 + float(s)
    except:
        return 0.0

def parse_srt(file_path):
    """
    Parse an SRT file into a list of entries:
    [{"index": int, "start": float(sec), "end": float(sec), "text": str, "text_raw": str}, ...]
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except UnicodeDecodeError:
        try:
            with open(file_path, 'r', encoding='gb18030') as f:
                content = f.read()
        except Exception as e:
            print(f"Error reading SRT: {e}")
            return []

    content = content.lstrip('\ufeff')
    entries = []

    blocks = re.split(r'\n\s*\n', content.strip())
    for block in blocks:
        lines = [l.rstrip() for l in block.splitlines() if l.strip()]
        if len(lines) < 2:
            continue
        idx = None
        try:
            idx = int(lines[0].strip())
        except:
            pass
        time_line = None
        text_lines_start = 1
        m = re.search(r'(\d{1,2}:\d{2}:\d{2}[,\.]\d{1,3})\s*-->\s*(\d{1,2}:\d{2}:\d{2}[,\.]\d{1,3})', lines[0])
        if m:
            time_line = lines[0]
            text_lines_start = 1
        elif len(lines) >= 2:
            m2 = re.search(r'(\d{1,2}:\d{2}:\d{2}[,\.]\d{1,3})\s*-->\s*(\d{1,2}:\d{2}:\d{2}[,\.]\d{1,3})', lines[1])
            if m2:
                time_line = lines[1]
                text_lines_start = 2
                try:
                    idx = int(lines[0].strip())
                except:
                    pass
        if not time_line:
            continue
        tm = re.search(r'(\d{1,2}:\d{2}:\d{2}[,\.]\d{1,3})\s*-->\s*(\d{1,2}:\d{2}:\d{2}[,\.]\d{1,3})', time_line)
        if not tm:
            continue
        start_s = parse_srt_time(tm.group(1))
        end_s = parse_srt_time(tm.group(2))
        text_parts = lines[text_lines_start:]
        raw_text = " ".join(text_parts).strip()
        clean_txt = re.sub(r'<[^>]+>', '', raw_text)
        clean_txt = re.sub(r'\s+', ' ', clean_txt).strip()
        entries.append({
            "index": idx if idx is not None else len(entries)+1,
            "start": start_s,
            "end": end_s,
            "text": clean_txt,
            "text_raw": raw_text
        })

    if entries:
        print(f"[DEBUG] Parsed {len(entries)} SRT entries.")
        e = entries[0]
        print(f"[DEBUG] First entry: #{e['index']} [{e['start']:.3f}s -> {e['end']:.3f}s] Text: '{e['text'][:40]}...'")
    return entries

# --- SRT + TXT -> New FCPXML Generator ---
def srt_time_to_fcp_secs(seconds, fps=24):
    """Convert float seconds to FCPXML time fraction string, e.g. '1234/24000s' or 'Ns'."""
    total_frames = int(round(seconds * fps))
    return f"{total_frames * 1000}/{fps * 1000}s"

def make_title_element(ref_id, lane, name, offset_str, duration_str, text_content, y_pos, font_size, ts_unique_id):
    """Build a <title> element with text-style, text-style-def, and Position param."""
    title = ET.Element("title", {
        "ref": ref_id,
        "lane": str(lane),
        "name": name[:60] if name else "Subtitle",
        "offset": offset_str,
        "duration": duration_str,
        "start": "0s"
    })
    ET.SubElement(title, "param", {
        "name": "Position",
        "key": "9999/999166631/999166633/1/100/101",
        "value": f"0 {y_pos}"
    })
    ET.SubElement(title, "param", {
        "name": "Alignment",
        "key": "9999/999166631/999166633/2/354/100/443",
        "value": "1"
    })
    text_el = ET.SubElement(title, "text")
    ts = ET.SubElement(text_el, "text-style", {"ref": ts_unique_id})
    ts.text = text_content
    ts_def = ET.SubElement(title, "text-style-def", {"id": ts_unique_id})
    ET.SubElement(ts_def, "text-style", {
        "font": "Alibaba PuHuiTi",
        "fontSize": str(font_size),
        "fontFace": "Regular",
        "fontColor": "1 1 1 1",
        "shadowColor": "0 0 0 0.75",
        "shadowOffset": "4 315",
        "alignment": "center"
    })
    return title

# --- Granularity Bridge Helpers ---
GRID_MAX_SRT_COMBO = 4          # max consecutive SRT entries to try combine -> 1 txt
GRID_MAX_TXT_MERGE = 6         # max consecutive TXT lines  to try merge   -> 1 srt
GRID_SRT_COMBO_MAX_GAP = 1.5   # max gap (s) between two SRTs to still consider merging them

def _split_time_window_by_chars(start_s, end_s, char_weights):
    """Given a time window [start_s, end_s], split into len(char_weights) sub-windows,
    proportional to each weight (usually char counts). Returns list of (s_start, s_end)."""
    n = len(char_weights)
    if n <= 0:
        return []
    if n == 1:
        return [(start_s, end_s)]
    total_w = sum(char_weights) or 1
    total_dur = max(0.05, end_s - start_s)
    segs = []
    acc = 0.0
    cursor = start_s
    for i, w in enumerate(char_weights):
        frac = w / total_w
        if i == n - 1:
            seg_end = end_s
        else:
            seg_end = start_s + total_dur * (acc + frac)
        segs.append((cursor, seg_end))
        cursor = seg_end
        acc += frac
    return segs

def generate_fcpxml_from_srt_and_txt(srt_entries_in, matched_pairs, output_path, fps=24,
                                     auto_zero_tc=True, granularity_align=True):
    """
    Generate a brand new FCPXML from (SRT timing + TXT correct text).

    Parameters
    ----------
    auto_zero_tc : bool
        If True, SUBTRACT the first SRT entry's start time from ALL entries.
        Universal fix for sources that start at 01:00:00 / 02:00:00 etc.

    granularity_align : bool
        If True, try both:
          * TXT multi-to-one merge   (multiple consecutive TXT lines match one SRT)  – when TXT is chopped finer
          * SRT combo (one-to-multi) (multiple consecutive SRTs match one TXT line)  – when SRT is chopped finer
        When a merge/combo wins, split the combined time window back into individual
        title clips by char-count ratio so every corrected sentence has its on-screen slot.
    """
    if not srt_entries_in:
        print("[ERROR] No SRT entries to generate.")
        return False
    n_pairs_all = len(matched_pairs)
    if n_pairs_all == 0:
        print("[ERROR] No TXT pairs loaded.")
        return False

    # ------- Step A. Smart TC zeroing -------
    srt_entries = [dict(e) for e in srt_entries_in]
    if auto_zero_tc:
        # Professional cameras often preset timecode to an integer hour floor
        # (01:00:00, 02:00:00, ...) for multi-camera sync.  We want to remove
        # ONLY that hour floor while preserving the real sub-hour offsets
        # (e.g. 01:00:00,500 -> 00:00:00,500  NOT  00:00:00,000).
        #
        # However, we must NOT subtract anything when the SRT truly starts in
        # the 00-hour range with a real, intentional pre-roll (e.g. the SRT
        # was authored from 0s, or someone already shifted it).  The rule:
        #   -> subtract hour-floor ONLY if the raw first-start is within 10
        #      minutes of that hour-floor (i.e. start lies in [H:00:00,
        #      H:10:00)).  For start >= 10 min within the hour we assume the
        #      offset is intentional and do NOT touch it.  If hour_floor == 0
        #      (00:xx:xx SRT) we never subtract 0 anyway, so it's a no-op.
        import math
        raw_first = srt_entries[0]["start"]
        hour_floor = math.floor(raw_first / 3600.0) * 3600.0
        within_10min_of_hour = (raw_first - hour_floor) < (10.0 * 60.0)
        offset = hour_floor if (hour_floor > 0 and within_10min_of_hour) else 0.0
        if offset > 0:
            for e in srt_entries:
                e["start"] = max(0.0, e["start"] - offset)
                e["end"]   = max(0.0, e["end"]   - offset)
            print(f"[INFO] Applied TC zeroing: subtract hour-floor = {offset:.3f}s "
                  f"(raw first-start = {raw_first:.3f}s, within 10min rule = {within_10min_of_hour}). "
                  f"New range: {srt_entries[0]['start']:.3f}s -> {srt_entries[-1]['end']:.3f}s")
        else:
            print(f"[INFO] TC zeroing skipped: raw first-start = {raw_first:.3f}s is not "
                  f"within 10min of a non-zero hour floor (hour_floor={hour_floor:.0f}s). "
                  f"Range preserved: {srt_entries[0]['start']:.3f}s -> {srt_entries[-1]['end']:.3f}s")

    n = len(srt_entries)
    total_sec = max(srt_entries[-1]["end"] + 2.0, 1.0)
    total_dur_str = srt_time_to_fcp_secs(total_sec, fps)
    frame_dur_attr = f"1/{fps}s"

    # ------- Step B. Build XML scaffold -------
    root = ET.Element("fcpxml", version="1.10")
    resources = ET.SubElement(root, "resources")
    ET.SubElement(resources, "format", {
        "id": "r1",
        "name": f"HD1080p{fps}",
        "frameDuration": frame_dur_attr,
        "width": "1920",
        "height": "1080"
    })
    ET.SubElement(resources, "effect", {
        "id": "r_title",
        "name": "Basic Title",
        "uid": ".../Titles.localized/Bumper:Opener.localized/Basic Title.localized/Basic Title.moti"
    })

    library = ET.SubElement(root, "library")
    event = ET.SubElement(library, "event", name="SRT_Timeline")
    project_name = os.path.splitext(os.path.basename(output_path))[0] or "SRT_Project"
    project = ET.SubElement(event, "project", name=project_name)
    sequence = ET.SubElement(project, "sequence", {
        "format": "r1",
        "tcStart": "0s",
        "tcFormat": "NDF",
        "duration": total_dur_str
    })
    spine = ET.SubElement(sequence, "spine")
    gap = ET.SubElement(spine, "gap", {
        "name": "Gap",
        "offset": "0s",
        "duration": total_dur_str,
        "start": "0s"
    })

    # ------- Step C. Matching: monotonic 1:1 alignment, THEN local rescue -------
    #
    # Philosophy (identical to match_duel v48 "find_match_complex"):
    #   Pass 0 (Granularity pre-bridge). Split overly-long TXT[j] that clearly correspond
    #          to multiple adjacent SRT sentences (SRT[i] + SRT[i+1] + ... ≈ TXT[j]), OR
    #          merge adjacent SRTs whose clean-text concat approximates 1 TXT. This
    #          eliminates the vast majority of "SRT granularity mismatches TXT" before
    #          any cursor-based 1:1 alignment even runs.
    #   Pass 1: Scan SRTs left-to-right with a forward-only cursor so TXT indices are
    #           strictly non-decreasing (no eating into later TXTs prematurely).
    #   Pass 2: Walk the 1:1 result again. For every entry that is still weak (<0.45),
    #           try ONLY locally:
    #             a) merge 1 SRT window : K contiguous unused TXTs right after anchor (merge_txt)
    #             b) combo current SRT + next SRT into 1 sentence : 1 TXT (combo_srt)
    #           choose whichever is best; if nothing works -> fallback.
    #   Pass 3: Global rescue for any still-unmatched SRT, accept any unused pair.

    # --- Pass 0: Granularity pre-bridge: expand matched_pairs for long TXT that match multiple short SRT ---
    def score_text(a, b):
        return get_similarity_v48(a, b)

    if granularity_align and len(srt_entries) > 0 and len(matched_pairs) > 0:
        new_matched_pairs = []
        i_srt = 0
        n = len(srt_entries)
        def _srt_clean(k):
            return clean_text_v48(srt_entries[k]["text"])
        def _pair_clean(t):
            return clean_text_v48(t)
        for j in range(len(matched_pairs)):
            p = matched_pairs[j]
            p_clean = _pair_clean(p["orig"])
            if i_srt >= n:
                new_matched_pairs.append(p)
                continue
            # Greedy: see if we can carve p_clean into K consecutive SRT clean texts (or near-matches)
            # Require p_clean length to be at least 1.5x one SRT clean, otherwise default single
            carved = []
            cur_pos = 0
            k_count = 0
            remaining = p_clean
            running_srt_idx = i_srt
            while remaining and running_srt_idx < n and k_count < GRID_MAX_TXT_MERGE:
                s_clean = _srt_clean(running_srt_idx)
                if not s_clean: break
                # Compute best alignment of s_clean as prefix of remaining
                # Use v48 scoring but restricted to LEFT prefix of remaining
                # Strategy: compute difflib.SequenceMatcher ratio between s_clean and remaining[:L]
                # for L in [max(1, len(s_clean)-4) ... min(len(remaining), len(s_clean)+10)]
                best_l = 0
                best_r = 0.0
                if len(remaining) <= len(s_clean) + 1 and score_text(srt_entries[running_srt_idx]["text"], p["orig"]) >= V48_HIGH_CONFIDENCE - 0.1:
                    # close enough to be single match; skip split
                    break
                scan_start_L = max(1, min(len(remaining), max(1, len(s_clean) - 6)))
                scan_end_L   = min(len(remaining), len(s_clean) + 12)
                if scan_end_L <= scan_start_L: scan_end_L = scan_start_L + 1
                import difflib
                for L in range(scan_start_L, scan_end_L + 1):
                    left = remaining[:L]
                    r = difflib.SequenceMatcher(None, s_clean, left).ratio()
                    if r > best_r:
                        best_r, best_l = r, L
                if best_r >= 0.40 and best_l > 0:
                    carved.append((best_l, running_srt_idx, best_r))
                    remaining = remaining[best_l:]
                    running_srt_idx += 1
                    k_count += 1
                else:
                    break
            if len(carved) >= 2 and len(remaining) <= max(6, int(0.30 * len(p_clean))):
                # Split p into k_count sub-pairs preserving original translation if any
                # Use char-offset proportional split on ORIGINAL (non-clean) text, so
                # punctuation / wording is preserved.
                fracs = []
                cur = 0
                tot = 0
                for (L, si, r) in carved:
                    fracs.append(L); tot += L
                if remaining:
                    fracs[-1] += len(remaining)   # tack leftover onto last slice
                    tot += len(remaining)
                txt_orig = p["orig"]
                txt_trans = p.get("trans") or ""
                # distribute proportional to tot ratio
                splits_orig = []
                splits_trans = []
                off_orig = 0
                off_trans = 0
                len_orig = len(txt_orig)
                len_trans = len(txt_trans)
                for kk, f in enumerate(fracs):
                    weight = f / tot
                    if kk == len(fracs) - 1:
                        so, eo = off_orig, len_orig
                        st, et = off_trans, len_trans
                    else:
                        take_o = max(1, int(round(len_orig * weight)))
                        take_t = max(1, int(round(len_trans * weight))) if len_trans > 0 else 0
                        eo = min(len_orig, off_orig + take_o)
                        et = min(len_trans, off_trans + take_t)
                        so = off_orig
                        st = off_trans
                    splits_orig.append(txt_orig[so:eo])
                    splits_trans.append(txt_trans[st:et] if len_trans > 0 else "")
                    off_orig = eo
                    off_trans = et
                for kk in range(len(carved)):
                    sub_pair = {
                        "orig": splits_orig[kk],
                        "trans": splits_trans[kk],
                        "_split_from": j,
                    }
                    new_matched_pairs.append(sub_pair)
                i_srt = running_srt_idx
            else:
                # single pair as-is; try to advance i_srt by 1 if a single strong match
                sc0 = score_text(srt_entries[i_srt]["text"], p["orig"])
                if sc0 >= 0.50:
                    i_srt += 1
                new_matched_pairs.append(p)
        # attach any remaining matched_pairs untouched (i_srt doesn't matter)
        # replace matched_pairs with expanded set, and update n_pairs_all
        matched_pairs = new_matched_pairs
        n_pairs_all = len(matched_pairs)
    n_pairs_all = len(matched_pairs)
    n = len(srt_entries)

    used_pair_indices = set()
    stats = {
        "matched_bilingual": 0,
        "matched_orig_only": 0,
        "unmatched": 0,
        "n_merge_txt": 0,
        "n_combo_srt": 0,
        "n_1to1": 0,
    }

    align_j = [None] * n       # align_j[srt_i] = pair_idx or None (Pass 1 result)
    align_score = [0.0] * n

    # ---- Pass 1: monotonic left-to-right 1:1 alignment ----
    cursor = 0
    import math
    for i in range(n):
        srt_t = srt_entries[i]["text"]
        search_from = cursor
        search_to = min(n_pairs_all, cursor + V48_SEARCH_WINDOW)
        best_sc = -1.0
        best_j = -1
        for jj in range(search_from, search_to):
            sc_raw = score_text(srt_t, matched_pairs[jj]["orig"])
            # Mild positional bias: bonus decays over 10 indices,
            # max 0.06 so a 0.82 true match still beats 0.40 noise at cursor.
            dist = abs(jj - cursor)
            pos_bonus = 0.06 * math.exp(-dist / 10.0)
            sc = sc_raw + pos_bonus
            if sc > best_sc:
                best_sc, best_j = sc, jj
                if sc_raw >= V48_HIGH_CONFIDENCE:
                    break
        if best_sc < V48_HIGH_CONFIDENCE:
            alt_from = max(0, cursor - 12)
            for jj in range(alt_from, search_from):
                if jj in used_pair_indices:
                    continue
                sc_raw = score_text(srt_t, matched_pairs[jj]["orig"])
                dist = abs(jj - cursor)
                pos_bonus = 0.06 * math.exp(-dist / 10.0) - 0.01
                sc = sc_raw + pos_bonus
                if sc > best_sc:
                    best_sc, best_j = sc, jj
        accept_sc = score_text(srt_t, matched_pairs[best_j]["orig"]) if best_j >= 0 else 0.0
        if best_j >= 0 and accept_sc >= 0.25:
            in_forward_window = best_j >= cursor and best_j < cursor + V48_SEARCH_WINDOW
            if (not in_forward_window) and accept_sc < 0.55:
                pass
            else:
                align_j[i] = best_j
                align_score[i] = accept_sc
                used_pair_indices.add(best_j)
                cursor = best_j + 1

    # ---- Pass 2: local rescue over align[] ----
    plan = []
    processed = [False] * n
    for i in range(n):
        if processed[i]:
            continue
        j = align_j[i]
        j_sc = align_score[i] if j is not None else 0.0
        strong = (j is not None) and (j_sc >= 0.45)
        candidates = []

        if strong:
            candidates.append({
                "srt_indices": [i],
                "pair_indices": [j],
                "score": j_sc,
                "type": "1:1",
            })

        if not strong and granularity_align:
            anchor_j = j
            # --- Strategy A: merge_txt (1 SRT : K contiguous TXTs from anchor) ---
            if anchor_j is None:
                bs = -1.0
                bj = -1
                st = max(0, cursor - V48_SEARCH_WINDOW)
                en = min(n_pairs_all, cursor + V48_SEARCH_WINDOW)
                for jj in range(st, en):
                    # Skip jj if it's permanently assigned (owner is an earlier, already-processed SRT)
                    owner = None
                    for xi in range(n):
                        if align_j[xi] == jj:
                            owner = xi
                            break
                    if owner is not None and processed[owner]:
                        continue
                    sc = score_text(srt_entries[i]["text"], matched_pairs[jj]["orig"])
                    if sc > bs:
                        bs = sc
                        bj = jj
                if bj >= 0 and bs >= 0.25:
                    anchor_j = bj
                    j_sc = bs
            if anchor_j is not None:
                merged = [anchor_j]
                best_merge_sc = j_sc
                best_merge_k = 1
                merged_txt = matched_pairs[anchor_j]["orig"]
                max_k = min(GRID_MAX_TXT_MERGE, n_pairs_all - anchor_j)
                for k in range(2, max_k + 1):
                    cand_j = anchor_j + k - 1
                    if cand_j >= n_pairs_all:
                        break
                    owner = None
                    for xi in range(n):
                        if align_j[xi] == cand_j:
                            owner = xi
                            break
                    # allow merge if unused, OR owner is later than i (we'll displace)
                    if owner is not None and owner < i and processed[owner]:
                        break
                    merged_txt = merged_txt + matched_pairs[cand_j]["orig"]
                    sc = score_text(srt_entries[i]["text"], merged_txt)
                    if sc > best_merge_sc + 0.03:
                        best_merge_sc = sc
                        best_merge_k = k
                        merged = list(range(anchor_j, anchor_j + k))
                ok_merge = True
                for jj in merged:
                    owner = None
                    for xi in range(n):
                        if align_j[xi] == jj:
                            owner = xi
                            break
                    if owner is not None and owner < i and processed[owner]:
                        ok_merge = False
                        break
                if ok_merge and best_merge_sc >= 0.35:
                    # 单调约束：merge 起点 anchor_j 不得明显落后于 cursor (最多允许回溯 8)
                    if merged[0] >= cursor - 8:
                        candidates.append({
                            "srt_indices": [i],
                            "pair_indices": merged,
                            "score": best_merge_sc,
                            "type": "merge_txt" if best_merge_k > 1 else "1:1",
                        })

            # --- Strategy B: combo_srt (K consecutive SRTs -> 1 TXT) ---
            combo_targets = []
            if anchor_j is not None:
                combo_targets.append(anchor_j)
            bs = -1.0
            bj = -1
            st = max(0, cursor - V48_SEARCH_WINDOW)
            en = min(n_pairs_all, cursor + V48_SEARCH_WINDOW)
            two_srt_text = srt_entries[i]["text"]
            if i + 1 < n:
                two_srt_text += srt_entries[i + 1]["text"]
            for jj in range(st, en):
                owner = None
                for xi in range(n):
                    if align_j[xi] == jj:
                        owner = xi
                        break
                if owner is not None and owner < i and processed[owner]:
                    continue
                sc = score_text(two_srt_text, matched_pairs[jj]["orig"])
                if sc > bs:
                    bs = sc
                    bj = jj
            if bj >= 0 and bj not in combo_targets:
                combo_targets.append(bj)
            for target_j in combo_targets:
                best_combo_sc = score_text(srt_entries[i]["text"], matched_pairs[target_j]["orig"])
                best_combo_k = 1
                combo_text = srt_entries[i]["text"]
                for k in range(2, GRID_MAX_SRT_COMBO + 1):
                    end_i = i + k - 1
                    if end_i >= n:
                        break
                    pe = srt_entries[end_i - 1]["end"]
                    ns = srt_entries[end_i]["start"]
                    if (ns - pe) > GRID_SRT_COMBO_MAX_GAP:
                        break
                    combo_text += srt_entries[end_i]["text"]
                    sc = score_text(combo_text, matched_pairs[target_j]["orig"])
                    if sc > best_combo_sc + 0.03:
                        best_combo_sc = sc
                        best_combo_k = k
                if best_combo_k > 1 and best_combo_sc >= 0.45:   # 提高阈值：combo 是高损失策略，必须非常确定
                    conflict = False
                    for si in range(i, i + best_combo_k):
                        if processed[si]:
                            conflict = True
                            break
                    if not conflict:
                        for xi in range(i):
                            if align_j[xi] == target_j and processed[xi]:
                                conflict = True
                                break
                    # 单调约束：target_j 不得早于 cursor - 8，防止向后回跳
                    if target_j < cursor - 8:
                        conflict = True
                    if not conflict:
                        candidates.append({
                            "srt_indices": list(range(i, i + best_combo_k)),
                            "pair_indices": [target_j],
                            "score": best_combo_sc,
                            "type": "combo_srt",
                        })

        # --- Choose winner ---
        chosen = None
        if candidates:
            candidates.sort(key=lambda c: c["score"], reverse=True)
            chosen = candidates[0]
            if chosen["score"] < 0.35:
                chosen = None

        if chosen is None:
            chosen = {
                "srt_indices": [i],
                "pair_indices": [],
                "score": 0.0,
                "type": "fallback",
                "fallback_text": srt_entries[i]["text"],
            }

        for jj in chosen["pair_indices"]:
            used_pair_indices.add(jj)
        for ii in chosen["srt_indices"]:
            processed[ii] = True
        if chosen["pair_indices"]:
            # Displace prior align[] for any pair_indices claimed here and owned by later SRTs
            for jj in chosen["pair_indices"]:
                for xi in range(n):
                    if align_j[xi] == jj and xi not in chosen["srt_indices"]:
                        align_j[xi] = None
                        align_score[xi] = 0.0
            for k, ii in enumerate(chosen["srt_indices"]):
                if k < len(chosen["pair_indices"]):
                    align_j[ii] = chosen["pair_indices"][k]
                    align_score[ii] = chosen["score"]
            cursor = max(cursor, max(chosen["pair_indices"]) + 1)

        plan.append(chosen)
        t = chosen["type"]
        if t == "1:1":
            stats["n_1to1"] += 1
        elif t == "merge_txt":
            stats["n_merge_txt"] += 1
        elif t in ("combo_srt", "grouped_align"):
            stats["n_combo_srt"] += 1

    # ---- Pass 3: global rescue for any remaining fallbacks ----
    # For every SRT i still not processed, try 1:1 over *all unused* pair indices
    # (no cursor restriction), then merge_txt, then combo_srt, accept first >= 0.30.
    for i in range(n):
        if processed[i]:
            continue
        srt_t = srt_entries[i]["text"]
        candidates = []
        # 1:1 over all unused
        best_sc, best_j = -1.0, -1
        for jj in range(n_pairs_all):
            if jj in used_pair_indices:
                continue
            sc = score_text(srt_t, matched_pairs[jj]["orig"])
            if sc > best_sc:
                best_sc, best_j = sc, jj
                if sc >= V48_HIGH_CONFIDENCE:
                    break
        if best_j >= 0 and best_sc >= 0.45:
            # monotonic guard: global rescues that go far back in j (before cursor - 12)
            # are almost always false positives.  Only accept if score is very high.
            ok = True
            if best_j < cursor - 12 and best_sc < 0.80:
                ok = False
            # low-confidence global jumps: reject even inside window if <0.55.
            if abs(best_j - cursor) >= 20 and best_sc < 0.70:
                ok = False
            if ok:
                candidates.append({
                    "srt_indices": [i], "pair_indices": [best_j],
                    "score": best_sc, "type": "1:1",
                })
                anchor_for_AB = best_j
                anchor_sc = best_sc
            else:
                anchor_for_AB = None
                anchor_sc = 0.0
        else:
            anchor_for_AB = None
            anchor_sc = 0.0
        if granularity_align and not candidates:
            # A. merge_txt: start from any unused jj as anchor, merge next up to 5
            if anchor_for_AB is None:
                # search any unused anchor anywhere with score >= 0.25
                gbs, gbj = -1.0, -1
                for jj in range(n_pairs_all):
                    if jj in used_pair_indices: continue
                    sc = score_text(srt_t, matched_pairs[jj]["orig"])
                    if sc > gbs: gbs, gbj = sc, jj
                if gbj >= 0 and gbs >= 0.25:
                    anchor_for_AB, anchor_sc = gbj, gbs
            if anchor_for_AB is not None:
                merged = [anchor_for_AB]
                best_msc = anchor_sc
                best_mk = 1
                merged_txt = matched_pairs[anchor_for_AB]["orig"]
                max_k = min(GRID_MAX_TXT_MERGE, n_pairs_all - anchor_for_AB)
                for k in range(2, max_k + 1):
                    cand_j = anchor_for_AB + k - 1
                    if cand_j in used_pair_indices: break
                    merged_txt = merged_txt + matched_pairs[cand_j]["orig"]
                    sc = score_text(srt_t, merged_txt)
                    if sc > best_msc + 0.03:
                        best_msc, best_mk = sc, k
                        merged = list(range(anchor_for_AB, anchor_for_AB + k))
                if best_msc >= 0.35 and (best_mk > 1 or best_msc >= 0.30):
                    candidates.append({
                        "srt_indices": [i], "pair_indices": merged,
                        "score": best_msc,
                        "type": "merge_txt" if best_mk > 1 else "1:1",
                    })
            # B. combo_srt: combine i..i+K-1 (if not processed) into 1 sentence vs 1 unused pair
            if not candidates:
                # 找最佳 single unused 匹配目标（先搜 i..i+2 组合的文本）
                bs, bj = -1.0, -1
                combo_text_all = srt_t
                for kk in range(1, GRID_MAX_SRT_COMBO):
                    if i + kk < n and not processed[i + kk]:
                        pe = srt_entries[i + kk - 1]["end"]
                        ns = srt_entries[i + kk]["start"]
                        if (ns - pe) <= GRID_SRT_COMBO_MAX_GAP:
                            combo_text_all += srt_entries[i + kk]["text"]
                for jj in range(n_pairs_all):
                    if jj in used_pair_indices: continue
                    sc = score_text(combo_text_all, matched_pairs[jj]["orig"])
                    if sc > bs: bs, bj = sc, jj
                if bj >= 0 and bs >= 0.25:
                    # 找到最佳 K
                    best_csc = score_text(srt_t, matched_pairs[bj]["orig"])
                    best_ck = 1
                    cur_ct = srt_t
                    for k in range(2, GRID_MAX_SRT_COMBO + 1):
                        end_i = i + k - 1
                        if end_i >= n or processed[end_i]: break
                        pe = srt_entries[end_i - 1]["end"]
                        ns = srt_entries[end_i]["start"]
                        if (ns - pe) > GRID_SRT_COMBO_MAX_GAP: break
                        cur_ct = cur_ct + srt_entries[end_i]["text"]
                        sc = score_text(cur_ct, matched_pairs[bj]["orig"])
                        if sc > best_csc + 0.03:
                            best_csc, best_ck = sc, k
                    if best_ck > 1 and best_csc >= 0.40:
                        candidates.append({
                            "srt_indices": list(range(i, i + best_ck)),
                            "pair_indices": [bj],
                            "score": best_csc, "type": "combo_srt",
                        })
        if candidates:
            candidates.sort(key=lambda c: c["score"], reverse=True)
            chosen = candidates[0]
            if chosen["score"] < 0.30:
                chosen = None
        else:
            chosen = None
        if chosen is None:
            # keep the fallback that was already appended in Pass 2; mark processed
            processed[i] = True
            # but note: plan item was already pushed in Pass 2 as fallback entry;
            # we need to find it and mark it as fallback no-change
            continue
        # Replace the matching Pass-2 fallback plan entry with chosen plan
        # Find plan index: the last plan step whose srt_indices[0] == i and type==fallback
        replace_idx = None
        for pi in range(len(plan) - 1, -1, -1):
            if plan[pi]["type"] == "fallback" and i in plan[pi]["srt_indices"]:
                replace_idx = pi; break
        # Mark processed, add to used_pair
        for jj in chosen["pair_indices"]: used_pair_indices.add(jj)
        for ii in chosen["srt_indices"]: processed[ii] = True
        if chosen["pair_indices"]:
            for kk, ii in enumerate(chosen["srt_indices"]):
                if kk < len(chosen["pair_indices"]):
                    align_j[ii] = chosen["pair_indices"][kk]
                    align_score[ii] = chosen["score"]
            cursor = max(cursor, max(chosen["pair_indices"]) + 1)
        # stats
        t = chosen["type"]
        if t == "1:1": stats["n_1to1"] += 1
        elif t == "merge_txt": stats["n_merge_txt"] += 1
        elif t in ("combo_srt",): stats["n_combo_srt"] += 1
        if replace_idx is not None:
            plan[replace_idx] = chosen
        else:
            plan.append(chosen)

    # ---- Pass 4: Hungarian-style small-window rescue for leftovers ----
    # Collect all remaining unprocessed SRT indices and all unused pair indices.
    # If the union is small (total <= 24 items), enumerate every possible
    # SRT combo (adjacent K SRTs merged into 1 sentence) and TXT merge
    # (adjacent J TXTs merged) then compute a max-weight bipartite matching
    # via DP (bitmask assignment).  This globally fixes tail cross-matches.
    #
    # Pass 4b first: release weak / low-confidence alignments (score < 0.50)
    # so we don't lock in 0.40-background-noise decisions.  This is generic:
    # any "borderline accept" will get a 2nd chance in the global optimal
    # assignment.
    if granularity_align:
        RELEASE_SCORE = 0.52
        # Only release items in the TAIL of the plan (last 18 SRT entries),
        # plus any contiguous region of SRT entries immediately preceding
        # a tail weak-aligned item if they share the same "low confidence"
        # cluster.  This preserves the large (already-correct) head of the
        # alignment while still fixing tail cross-matches.
        TAIL_START_SRT = max(0, n - 18)
        # Also include any SRT earlier than TAIL_START_SRT whose alignment
        # score < RELEASE_SCORE only if it's part of a "run" of weak SRTs
        # adjacent to the tail (i.e. if SRT[TAIL_START_SRT - 1] is also
        # weak, then include it and keep walking backward until a strong
        # alignment is found).
        true_tail_start = TAIL_START_SRT
        while true_tail_start > 0 and (align_j[true_tail_start - 1] is None or align_score[true_tail_start - 1] < RELEASE_SCORE + 0.04):
            true_tail_start -= 1
        for i in range(true_tail_start, n):
            # Force-release any fallback item in the tail (align_j is None),
            # even if processed[i] is already True (which would be a Pass-2
            # fallback that never got replaced).  Also release any low-score
            # real alignment so it can get a 2nd chance in the global opt.
            if align_j[i] is None:
                processed[i] = False
                align_score[i] = 0.0
                continue
            if align_score[i] < RELEASE_SCORE:
                jj = align_j[i]
                align_j[i] = None
                align_score[i] = 0.0
                used_pair_indices.discard(jj)
                processed[i] = False
        # Also release any non-monotonic pair in the tail region (regardless of score)
        last_j = -1
        for i in range(n):
            if align_j[i] is None:
                continue
            if align_j[i] <= last_j and i >= true_tail_start:
                jj = align_j[i]
                align_j[i] = None
                align_score[i] = 0.0
                used_pair_indices.discard(jj)
                processed[i] = False
                continue
            if align_j[i] > last_j:
                last_j = align_j[i]
    leftover_srt = [i for i in range(n) if not processed[i]]
    leftover_txt = [j for j in range(n_pairs_all) if j not in used_pair_indices]
    # Before running Pass-4 DP, scrub any pre-existing plan steps that
    # reference SRT indices we intend to re-match (leftover_srt).  This
    # prevents a single SRT from appearing in 2 plan items (double-use).
    if leftover_srt:
        leftover_set = set(leftover_srt)
        new_plan = []
        for step in plan:
            overlap = any(si in leftover_set for si in step["srt_indices"])
            if overlap:
                # Drop this step; also return its pair_indices back to the free pool
                for jj in step["pair_indices"]:
                    used_pair_indices.discard(jj)
                for ii in step["srt_indices"]:
                    processed[ii] = False
                    align_j[ii] = None
                    align_score[ii] = 0.0
            else:
                new_plan.append(step)
        plan = new_plan
        # Re-compute leftovers after scrub (may grow slightly)
        leftover_srt = [i for i in range(n) if not processed[i]]
        leftover_txt = [j for j in range(n_pairs_all) if j not in used_pair_indices]
    if granularity_align and leftover_srt and leftover_txt:
        LS = len(leftover_srt)
        LT = len(leftover_txt)
        if max(LS, LT) <= 16:
            # --- generate every possible SRT "super item" as (mask, combined_text, score_map helper) ---
            # A super-item is a contiguous run over leftover_srt's positions.
            # Each SRT super-item represents "1 sentence" that should align to 1 TXT item.
            # Similarly TXT super-items are contiguous runs over leftover_txt.
            srt_supers = []   # list of (mask_bitmask_LS, srt_idx_list_0based_in_full)
            for a in range(LS):
                combined_text = ""
                srt_list = []
                gap_ok = True
                for b in range(a, LS):
                    srt_idx = leftover_srt[b]
                    if b > a:
                        prev_srt = leftover_srt[b-1]
                        if prev_srt + 1 != srt_idx:
                            gap_ok = False
                            break
                        pe = srt_entries[prev_srt]["end"]
                        ns = srt_entries[srt_idx]["start"]
                        if (ns - pe) > GRID_SRT_COMBO_MAX_GAP:
                            gap_ok = False
                            break
                    if not gap_ok:
                        break
                    combined_text += srt_entries[srt_idx]["text"]
                    srt_list.append(srt_idx)
                    K = b - a + 1
                    if K <= GRID_MAX_SRT_COMBO:
                        mask = 0
                        for xi in range(a, b + 1): mask |= (1 << xi)
                        srt_supers.append((mask, list(srt_list), combined_text))
                    else:
                        break
            txt_supers = []    # list of (mask_bitmask_LT, txt_idx_list_full, combined_text)
            for a in range(LT):
                combined_text = ""
                txt_list = []
                for b in range(a, LT):
                    txt_idx = leftover_txt[b]
                    if b > a and (txt_idx != leftover_txt[b-1] + 1):
                        break
                    combined_text += matched_pairs[txt_idx]["orig"]
                    txt_list.append(txt_idx)
                    K = b - a + 1
                    if K <= GRID_MAX_TXT_MERGE:
                        mask = 0
                        for xi in range(a, b + 1): mask |= (1 << xi)
                        txt_supers.append((mask, list(txt_list), combined_text))
                    else:
                        break
            # Build bipartite weight: srt_super i -> txt_super j  = score if >= 0.35 else 0
            SUP_I = len(srt_supers)
            SUP_J = len(txt_supers)
            W = [[0.0] * SUP_J for _ in range(SUP_I)]
            for i, (msk_s, srt_list, s_text) in enumerate(srt_supers):
                for j, (msk_t, txt_list, t_text) in enumerate(txt_supers):
                    sc = score_text(s_text, t_text)
                    # Allow K:K mixed matching only for very small K (1:1, 2:1, 1:2, 2:2, 3:1, 1:3)
                    # so that K*K <= 6; this allows cases like "最后 + 在冰滴咖啡" =>
                    # "最后在冰滴咖啡明亮的 + 柑橘酸和轻苦调中" merged.
                    if len(srt_list) > 1 and len(txt_list) > 1:
                        if (len(srt_list) * len(txt_list)) > 4:
                            continue
                    if sc >= 0.42:
                        # prefer smaller combos (1:1 over 2:1, etc.) with tiny penalty
                        penalty = 0.01 * (len(srt_list) + len(txt_list) - 2)
                        W[i][j] = sc - penalty
            # DP over bitmask of used_LS and used_LT.
            # state = (used_LS_mask_bits << 16) | used_LT_mask_bits
            # use DP dictionary to save memory.
            from collections import defaultdict
            FULL_S = (1 << LS) - 1
            FULL_T = (1 << LT) - 1
            dp = {}
            dp[(0, 0)] = (0.0, None, None)
            # Process items one-by-one, for each state try all srt_supers fitting the unused bits
            for usedS in range(FULL_S + 1):
                for usedT in range(FULL_T + 1):
                    state = (usedS, usedT)
                    if state not in dp:
                        continue
                    cur_sc, _, _ = dp[state]
                    # Transition: try a pair (si, tj) where srt_super s's mask & usedS == 0
                    # and txt_super t's mask & usedT == 0. Record best per resulting state.
                    for si in range(SUP_I):
                        mS, srt_list, _st = srt_supers[si]
                        if (mS & usedS) != 0:
                            continue
                        for tj in range(SUP_J):
                            mT, txt_list, _tt = txt_supers[tj]
                            if (mT & usedT) != 0:
                                continue
                            w = W[si][tj]
                            if w <= 0.0:
                                continue
                            newS = usedS | mS
                            newT = usedT | mT
                            new_sc = cur_sc + w
                            nxt = (newS, newT)
                            if nxt not in dp or dp[nxt][0] < new_sc:
                                dp[nxt] = (new_sc, state, (si, tj))
            # Find best state that covers as many bits as possible (pref FULL_S covered, then max score)
            best = None
            best_score = -1e9
            for (uS, uT), (sc, _, _) in dp.items():
                rank = 10000 * bin(uS).count("1") + sc   # maximize SRT coverage first, then score
                if rank > best_score:
                    best_score = rank
                    best = (uS, uT, sc)
            if best is not None and (bin(best[0]).count("1") > 0):
                # Backtrack
                uS, uT, _ = best
                steps_chosen = []
                cur = (uS, uT)
                while cur != (0, 0):
                    _, prev, act = dp[cur]
                    if act is not None:
                        si, tj = act
                        mS, srt_idx_list, _ = srt_supers[si]
                        mT, txt_idx_list, _ = txt_supers[tj]
                        sc2 = score_text(
                            "".join(srt_entries[xi]["text"] for xi in srt_idx_list),
                            "".join(matched_pairs[xj]["orig"] for xj in txt_idx_list)
                        )
                        if len(srt_idx_list) >= 2 and len(txt_idx_list) == 1:
                            ttype = "combo_srt"
                        elif len(txt_idx_list) >= 2 and len(srt_idx_list) == 1:
                            ttype = "merge_txt"
                        elif len(txt_idx_list) >= 2 and len(srt_idx_list) >= 2:
                            ttype = "grouped_align"
                        else:
                            ttype = "1:1"
                        steps_chosen.append({
                            "srt_indices": srt_idx_list,
                            "pair_indices": txt_idx_list,
                            "score": sc2,
                            "type": ttype,
                        })
                    cur = prev
                steps_chosen.reverse()
                # Apply each step: mark processed, used_pair, replace fallback plan item, stats.
                for step in steps_chosen:
                    if step["score"] < 0.42:
                        continue
                    # consistency: ensure no overlap with existing used_pair_indices
                    conflict = False
                    for jj in step["pair_indices"]:
                        if jj in used_pair_indices:
                            conflict = True; break
                    if conflict: continue
                    for ii in step["srt_indices"]:
                        if processed[ii]: conflict = True; break
                    if conflict: continue
                    # Good, apply
                    for jj in step["pair_indices"]:
                        used_pair_indices.add(jj)
                    for ii in step["srt_indices"]:
                        processed[ii] = True
                        # mark align_j / align_score for diagnostics
                        if step["pair_indices"]:
                            align_j[ii] = step["pair_indices"][0]
                            align_score[ii] = step["score"]
                    if step["pair_indices"]:
                        cursor = max(cursor, max(step["pair_indices"]) + 1)
                    # Replace plan items for srt_indices that were previously fallback
                    removed_plans = set()
                    for ii in step["srt_indices"]:
                        replace_idx = None
                        for pi in range(len(plan) - 1, -1, -1):
                            if pi in removed_plans: continue
                            if plan[pi]["type"] == "fallback" and ii in plan[pi]["srt_indices"]:
                                replace_idx = pi; break
                        if replace_idx is None:
                            continue
                        # Mark this plan index as replaced; we'll pop the first and insert step.
                        removed_plans.add(replace_idx)
                    # Insert new plan item at the earliest removed plan position (preserving order),
                    # and pop all removed fallback entries (sorted descending for deletion).
                    if removed_plans:
                        insert_pos = min(removed_plans)
                        for pi in sorted(removed_plans, reverse=True):
                            plan.pop(pi)
                        plan.insert(insert_pos, step)
                    else:
                        plan.append(step)
                    # stats
                    t = step["type"]
                    if t == "1:1": stats["n_1to1"] += 1
                    elif t == "merge_txt": stats["n_merge_txt"] += 1
                    elif t == "combo_srt": stats["n_combo_srt"] += 1
                    # Don't double count fallbacks we removed (they're not in the final count anyway)

    processed_srt_indices = set(i for i in range(n) if processed[i])

    # ---- Pass 5: collect unused TXT pairs and merge them into the nearest plan ----
    # step (prepend / append as merge_txt).  SRT is the "time skeleton" only;
    # the corrected TXT content is authoritative and must appear fully even if
    # the SRT (noisy ASR draft) missed a sentence boundary.  Any TXT pair that
    # no plan step references gets appended to the plan step whose already-used
    # TXT range is immediately before it (j+1 gap), or prepended if it's the
    # very first gap at j=0..anchor-1.
    unused_txt = sorted([j for j in range(n_pairs_all) if j not in used_pair_indices])
    if unused_txt:
        # group unused j into contiguous runs
        runs = []
        cur_start = unused_txt[0]
        cur_prev = unused_txt[0]
        for j in unused_txt[1:]:
            if j == cur_prev + 1:
                cur_prev = j
            else:
                runs.append((cur_start, cur_prev))
                cur_start = j
                cur_prev = j
        runs.append((cur_start, cur_prev))
        for rs, re in runs:
            run_count = re - rs + 1
            # Find anchor plan step: the plan that "owns" the TXT index just
            # before rs (anchor_bef), or the first plan step with any TXT after
            # re (anchor_aft).  Prefer anchor_bef so the unused sentences land
            # in their correct place in narrative order.
            anchor_idx = None  # index in plan[]
            anchor_side = None  # 'pre' | 'post'
            # Build map: for each plan step with pair_indices, find min/max j range
            step_ranges = []
            for pi, step in enumerate(plan):
                if step.get("pair_indices"):
                    step_ranges.append((pi, min(step["pair_indices"]), max(step["pair_indices"])))
            # anchor_bef: step with max_j < rs, choose largest max_j (closest)
            best_bef = -1; best_bef_pi = None
            for pi, mn, mx in step_ranges:
                if mx < rs and mx > best_bef:
                    best_bef = mx; best_bef_pi = pi
            if best_bef_pi is not None:
                anchor_idx = best_bef_pi
                anchor_side = "post"
            else:
                best_aft = 10**9; best_aft_pi = None
                for pi, mn, mx in step_ranges:
                    if mn > re and mn < best_aft:
                        best_aft = mn; best_aft_pi = pi
                if best_aft_pi is not None:
                    anchor_idx = best_aft_pi
                    anchor_side = "pre"
            if anchor_idx is None:
                continue  # should not happen
            # Don't append/prepend to fallback or grouped_align/combo that already have >6 TXT items
            target_step = plan[anchor_idx]
            if len(target_step.get("pair_indices", [])) + run_count > GRID_MAX_TXT_MERGE:
                # If too full, try next/prev neighbor; if still no room, skip (rare)
                continue
            new_pairs = list(range(rs, re + 1))
            new_srt = list(target_step["srt_indices"])
            merged_text = "".join(matched_pairs[xj]["orig"] for xj in new_pairs)
            anchor_text = "".join(matched_pairs[xj]["orig"] for xj in target_step["pair_indices"])
            sc_merge = score_text(
                "".join(srt_entries[xi]["text"] for xi in new_srt),
                anchor_text + merged_text if anchor_side == "post" else merged_text + anchor_text
            )
            if anchor_side == "post":
                new_pair_indices = list(target_step["pair_indices"]) + new_pairs
            else:
                new_pair_indices = new_pairs + list(target_step["pair_indices"])
            new_type = "merge_txt" if len(new_srt) == 1 else (
                "grouped_align" if len(new_pair_indices) > 1 else target_step["type"]
            )
            if len(new_pair_indices) > 1 and len(new_srt) == 1:
                new_type = "merge_txt"
            elif len(new_pair_indices) == 1 and len(new_srt) >= 2:
                new_type = "combo_srt"
            elif len(new_pair_indices) > 1 and len(new_srt) > 1:
                new_type = "grouped_align"
            else:
                new_type = "1:1"
            new_score = max(target_step.get("score", 0.0), sc_merge)
            replaced_step = {
                "srt_indices": list(new_srt),
                "pair_indices": new_pair_indices,
                "score": new_score,
                "type": new_type,
            }
            if target_step.get("fallback_text"):
                replaced_step["fallback_text"] = target_step["fallback_text"]
            # Mark new pairs used
            for jj in new_pairs:
                used_pair_indices.add(jj)
            plan[anchor_idx] = replaced_step

    # ------- Step D. Render plan -> titles with proportional time split -------
    ts_counter = 0
    n_plan = len(plan)
    printed_rows = 0
    for p_idx, step in enumerate(plan):
        win_start = srt_entries[step["srt_indices"][0]]["start"]
        win_end   = srt_entries[step["srt_indices"][-1]]["end"]
        srt_count = len(step["srt_indices"])
        txt_count = len(step["pair_indices"])

        if step["type"] == "fallback":
            slot_orig  = [step["fallback_text"]]
            slot_trans = [""]
            slot_times = [(win_start, win_end)]
            stats["unmatched"] += 1
            print_row = True
        else:
            orgs  = [matched_pairs[jj]["orig"]  for jj in step["pair_indices"]]
            trans = [matched_pairs[jj]["trans"] for jj in step["pair_indices"]]

            if step["type"] == "grouped_align" and srt_count == txt_count and srt_count >= 2:
                # K SRT : K TXT — each pair retains its own SRT time window
                slot_orig  = orgs
                slot_trans = trans
                slot_times = [
                    (srt_entries[si]["start"], srt_entries[si]["end"])
                    for si in step["srt_indices"]
                ]
            elif step["type"] == "merge_txt" and txt_count > 1 and srt_count == 1:
                # 1 SRT : K TXT — split 1 window among K sentences by char ratio
                weights = [max(1, len(clean_text_v48(o))) for o in orgs]
                slot_times = _split_time_window_by_chars(win_start, win_end, weights)
                slot_orig  = orgs
                slot_trans = trans
            elif step["type"] == "combo_srt" and srt_count > 1 and txt_count == 1:
                # legacy combo (rare now): K SRT : 1 TXT -> keep one sentence, full span
                slot_orig  = ["".join(orgs)]
                slot_trans = ["".join(trans)]
                slot_times = [(win_start, win_end)]
            else:
                # 1:1 default
                slot_orig  = orgs
                slot_trans = trans
                slot_times = [(win_start, win_end)]

            if all(t == "" for t in slot_trans):
                stats["matched_orig_only"] += 1
            else:
                stats["matched_bilingual"] += 1
            print_row = True

        if print_row and printed_rows < 200:
            srt_span_s = step["srt_indices"][0] + 1
            srt_span_e = step["srt_indices"][-1] + 1
            pair_span_s = step["pair_indices"][0] + 1 if step["pair_indices"] else "-"
            pair_span_e = step["pair_indices"][-1] + 1 if step["pair_indices"] else "-"
            type_tag = step["type"].ljust(13)
            first_srt_text = srt_entries[step["srt_indices"][0]]["text"]
            preview_src = first_srt_text[:28] + ("..." if len(first_srt_text) > 28 else "")
            first_orig = slot_orig[0]
            preview_orig = first_orig[:28] + ("..." if len(first_orig) > 28 else "")
            print(f"  [{p_idx+1:>3}/{n_plan}] {type_tag} SRT[{srt_span_s:>2}-{srt_span_e:<2}] TXT[{pair_span_s:>2}-{pair_span_e:<2}] "
                  f"Score {step['score']:.2f}  SRT: {preview_src}  =>  TXT: {preview_orig}")
            printed_rows += 1

        for slot_i, (s_start, s_end) in enumerate(slot_times):
            dur = max(0.1, s_end - s_start)
            start_str = srt_time_to_fcp_secs(s_start, fps)
            dur_str   = srt_time_to_fcp_secs(dur, fps)
            orig_d  = slot_orig[slot_i]  if slot_i < len(slot_orig)  else ""
            trans_d = slot_trans[slot_i] if slot_i < len(slot_trans) else ""
            if not orig_d:
                continue

            ts_counter += 1
            title_orig = make_title_element(
                ref_id="r_title", lane=1, name=orig_d,
                offset_str=start_str, duration_str=dur_str, text_content=orig_d,
                y_pos=-450, font_size=52, ts_unique_id=f"ts_orig_{ts_counter}",
            )
            gap.append(title_orig)
            if trans_d:
                ts_counter += 1
                title_trans = make_title_element(
                    ref_id="r_title", lane=2, name=trans_d,
                    offset_str=start_str, duration_str=dur_str, text_content=trans_d,
                    y_pos=-502, font_size=int(round(52 * 0.66)),
                    ts_unique_id=f"ts_trans_{ts_counter}",
                )
                title_trans.set("role", "EN.EN-1")
                gap.append(title_trans)

    # ------- Step E. Write file -------
    xml_bytes = ET.tostring(root, encoding="utf-8", xml_declaration=False)
    try:
        from xml.dom import minidom
        pretty = minidom.parseString(xml_bytes).toprettyxml(indent="  ")
        lines = pretty.split("\n")
        if lines and lines[0].startswith("<?xml"):
            lines = lines[1:]
        body = "\n".join(lines)
    except Exception:
        body = xml_bytes.decode("utf-8")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE fcpxml>\n')
        f.write(body)

    print("\n" + "=" * 50)
    print("  GENERATION SUMMARY")
    print("=" * 50)
    print(f"  Plan steps (merged/combo counted once) : {n_plan}")
    print(f"  SRT entries consumed                   : {n}")
    print(f"  ├─ 1:1 matches                         : {stats['n_1to1']}")
    print(f"  ├─ TXT multi-to-one merges             : {stats['n_merge_txt']}")
    print(f"  └─ SRT combo one-to-multi              : {stats['n_combo_srt']}")
    print(f"  Output title clips:                    : {ts_counter}")
    print(f"  Matched (bilingual)                    : {stats['matched_bilingual']}")
    print(f"  Matched (orig only / mono TXT)         : {stats['matched_orig_only']}")
    print(f"  Unmatched (SRT fallback)               : {stats['unmatched']}")
    total_ok = stats['matched_bilingual'] + stats['matched_orig_only']
    cover = (total_ok / n_plan * 100) if n_plan else 0
    print(f"  Plan step match coverage              : {cover:.1f}%")
    print(f"  Timeline total length                 : {total_sec:.1f}s  (FPS: {fps})")
    print("=" * 50)
    stats["total_srt"] = n
    stats["output_titles"] = ts_counter
    stats["coverage_pct"] = round(cover, 1)
    stats["total_sec"] = round(total_sec, 1)
    stats["fps"] = fps
    return True, stats


# --- Text Parsing Logic ---
def is_chinese(text):
    """Check if text contains Chinese characters."""
    return bool(re.search(r'[\u4e00-\u9fa5]', text))

def _is_likely_latin_sentence(text):
    """Heuristic: a line is likely a translation (English/Latin) if most of its letters are a-z/A-Z and contains spaces."""
    if not text:
        return False
    letters = re.findall(r'[A-Za-z]', text)
    cjk = re.findall(r'[\u4e00-\u9fa5]', text)
    total_nonspace = len(re.findall(r'\S', text)) or 1
    if len(cjk) > 0:
        return False
    if len(letters) / total_nonspace >= 0.5:
        return True
    return False

def parse_bilingual_text(file_path, mode="auto"):
    """
    Parses a text file into bilingual pairs.

    mode:
      "bilingual" -> Strict 2-line structure (Line1: Original, Line2: Translation)
      "mono"      -> Monolingual (every non-empty line is 'orig', trans="")
      "auto"      -> Detect by scanning: if >= 60% of EVEN lines (pair[1]) are Latin-dominant,
                     treat as bilingual; otherwise treat as monolingual (all lines are orig)
    """
    ext = os.path.splitext(file_path)[1].lower()
    content = ""

    if ext in ['.rtf', '.doc', '.docx']:
        try:
            result = subprocess.check_output(['textutil', '-convert', 'txt', '-stdout', file_path])
            content = result.decode('utf-8')
        except Exception as e:
            print(f"Warning: Failed to convert {ext} file using textutil: {e}")
            return []
    else:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except UnicodeDecodeError:
            with open(file_path, 'r', encoding='gb18030') as f:
                content = f.read()

    content = content.lstrip('\ufeff')
    raw_lines = content.splitlines()
    lines = [l.strip() for l in raw_lines if l.strip()]

    if mode == "auto":
        # Sample first up to 20 pairs; see if "line2" looks like translation (Latin, no CJK)
        sample_n = min(len(lines) // 2, 20)
        if sample_n >= 3:
            latin_hits = 0
            for k in range(sample_n):
                candidate_trans = lines[2*k + 1]
                if _is_likely_latin_sentence(candidate_trans):
                    latin_hits += 1
            if (latin_hits / sample_n) >= 0.6:
                mode = "bilingual"
            else:
                mode = "mono"
        elif len(lines) >= 2 and _is_likely_latin_sentence(lines[1]):
            mode = "bilingual"
        else:
            mode = "mono"
        print(f"[INFO] TXT auto-detected mode: {mode.upper()}  (sampled {sample_n} pairs)")

    pairs = []
    if mode == "mono":
        for ln in lines:
            pairs.append({"orig": ln, "trans": ""})
    else:  # bilingual
        i = 0
        while i < len(lines):
            line1 = lines[i]
            line2 = ""
            if i + 1 < len(lines):
                line2 = lines[i+1]
                pairs.append({"orig": line1, "trans": line2})
                i += 2
            else:
                pairs.append({"orig": line1, "trans": ""})
                i += 1

    if pairs:
        preview_o = pairs[0]["orig"][:30]
        preview_t = pairs[0]["trans"][:30] if pairs[0]["trans"] else "(empty / mono)"
        print(f"[DEBUG] TXT mode={mode}  First pair -> Orig: '{preview_o}...' | Trans: '{preview_t}...'")
    else:
        print("[DEBUG] WARNING: 0 pairs loaded! Check if TXT line endings or BOM encoding.")

    return pairs

# --- FCPXML Logic ---
def get_text_from_title(title_element):
    """Extracts ALL text content from a title element, including multiple text-style segments,
    with proper whitespace and Chinese punctuation normalization."""
    text_elem = title_element.find("text")
    if text_elem is not None:
        parts = []
        
        # Helper to clean and collect a segment
        def _add(seg):
            if seg:
                s = seg.strip()
                if s:
                    parts.append(s)
                    
        # Collect text from text node itself
        _add(text_elem.text)
            
        # Iterate ALL text-style children and collect their text + tail
        for ts in text_elem.findall("text-style"):
            _add(ts.text)
            _add(ts.tail)
                
        # Also collect text from any direct children (defensive)
        for child in list(text_elem):
            if child.tag != "text-style":
                _add(child.text)
                _add(child.tail)
                    
        # Join all clean parts without space first (Chinese segments stick together)
        full_text = ''.join(parts)
        
        # Pass 1: Remove spaces immediately adjacent to Chinese punctuation
        # Chinese punctuation list: ，。！？、；：""''（）【】《》—……·、
        cn_punct = r'，。！？、；：“”‘’（）【】《》—…·、,\\.!\\?;:"\'\\(\\)\\[\\]<>\\-'
        full_text = re.sub(r'\s+([' + cn_punct + r'])', r'\1', full_text)
        full_text = re.sub(r'([' + cn_punct + r'])\s+', r'\1', full_text)
        
        # Pass 2: For remaining whitespace (likely between English words), collapse to single space
        full_text = re.sub(r'[ \t]+', ' ', full_text)
        
        # Strip leading/trailing and return
        return full_text.strip()
    return ""

def set_text_to_title(title_element, new_text):
    """Sets text content to a title element, clearing any existing noise."""
    text_elem = title_element.find("text")
    if text_elem is not None:
        # Clear all text/tails in children to avoid repetition
        for child in list(text_elem):
            child.text = None
            child.tail = None
        text_elem.text = None
        text_elem.tail = None
        
        # Now set the new text
        ts = text_elem.find("text-style")
        if ts is not None:
            ts.text = new_text
        else:
            # If no text-style exists, create one or set directly
            text_elem.text = new_text

def update_position(title_element, target_y):
    """Sets the Y position of a title element to an absolute value."""
    # Pattern to match coordinate pairs like "0 -439.357"
    coord_pattern = re.compile(r'^(-?\d+\.?\d*)\s+(-?\d+\.?\d*)$')
    
    # Priority List: which params to check first
    priority_params = ["position", "offset"]
    
    # 1. Search all 'param' elements with priority names
    for p_name in priority_params:
        for param in title_element.iter("param"):
            name = param.get("name", "").lower()
            pid = param.get("id", "").lower()
            if p_name in name or p_name in pid:
                val = param.get("value", "")
                match = coord_pattern.match(val)
                if match:
                    try:
                        x = float(match.group(1))
                        param.set("value", f"{x} {target_y}")
                        return True # Stop after FIRST success
                    except:
                        pass
    
    # 2. Fallback: Search for any element with a 'value' that looks like coords
    for elem in title_element.iter():
        val = elem.get("value", "")
        match = coord_pattern.match(val)
        if match:
            try:
                x = float(match.group(1))
                elem.set("value", f"{x} {target_y}")
                return True # Stop after FIRST success
            except:
                pass
                    
    return False

def update_font_size(title_element, scale=0.66):
    """Updates the font size in text-style-def."""
    # <text-style-def id="...">
    #   <text-style ... fontSize="52" ... />
    # </text-style-def>
    ts_def = title_element.find("text-style-def")
    if ts_def is not None:
        ts = ts_def.find("text-style")
        if ts is not None:
            curr_size = ts.get("fontSize")
            if curr_size:
                try:
                    new_size = float(curr_size) * scale
                    ts.set("fontSize", str(new_size))
                except:
                    pass

def extract_subtitles_to_txt(xml_path, output_txt_path):
    """Extracts all subtitles from FCPXML to a TXT file."""
    # Resolve .fcpxmld path
    if xml_path.endswith(".fcpxmld"):
        info_path = os.path.join(xml_path, "Info.fcpxml")
        if os.path.exists(info_path):
            xml_path = info_path
        else:
            print(f"Error: {info_path} not found inside bundle.")
            return

    try:
        tree = ET.parse(xml_path)
    except Exception as e:
        print(f"Error parsing XML: {e}")
        return

    root = tree.getroot()
    subtitles = []

    # Find all titles
    for title in root.iter("title"):
        txt = get_text_from_title(title)
        if txt:
            # Clean up newlines if any
            clean_txt = txt.replace('\n', ' ').strip()
            if clean_txt:
                subtitles.append(clean_txt)

    if not subtitles:
        print("No subtitles found.")
        return

    with open(output_txt_path, 'w', encoding='utf-8') as f:
        for sub in subtitles:
            f.write(sub + "\n")
        
        # Add Prompt at the end
        f.write("以上中文修改错别字，并翻译成英文，并严格按照我给的文本分行，以一行中文一行英文的形式反馈给我，注意不是整段。再给我一个一键复制的按钮\n")

    print(f"Extracted {len(subtitles)} subtitles to {output_txt_path}")

def select_file_from_list(extensions, prompt_text="Enter file number or path: "):
    """
    Lists files matching extensions and allows user to select by number.
    Returns the selected file path.
    """
    print(f"\n[Available files in {os.getcwd()}]:")
    files = [f for f in os.listdir('.') if any(f.lower().endswith(ext) for ext in extensions)]
    files.sort()
    
    file_map = {}
    if files:
        for idx, f in enumerate(files, 1):
            print(f" {idx}. {f}")
            file_map[str(idx)] = f
    else:
        print(" (None found)")
    print("-" * 30)
    
    user_input = input(prompt_text).strip()
    user_input = user_input.replace('"', '').replace("'", "")
    
    # Check if user entered a number
    if user_input in file_map:
        selected_file = file_map[user_input]
        print(f"Selected: {selected_file}")
        return os.path.abspath(selected_file)
    
    # Otherwise assume it's a path
    return user_input

def add_bilingual_subs(xml_path, text_pairs, output_path):
    # Resolve .fcpxmld path
    if xml_path.endswith(".fcpxmld"):
        info_path = os.path.join(xml_path, "Info.fcpxml")
        if os.path.exists(info_path):
            xml_path = info_path
        else:
            print(f"Error: {info_path} not found inside bundle.")
            return

    tree = ET.parse(xml_path)
    root = tree.getroot()

    # Identify subtitles
    # We look for <title> elements.
    # They can be nested in <spine> -> <asset-clip> -> <title>
    # Or directly in <spine> -> <title>

    # Collect all titles first to avoid modifying tree while iterating
    # Note: element.iter("title") finds all titles at any depth
    all_titles = []
    parent_map = {c: p for p in root.iter() for c in p}

    for title in root.iter("title"):
        # Filter: Must have text content
        txt = get_text_from_title(title)
        if txt:
            all_titles.append(title)

    print(f"Found {len(all_titles)} subtitles in FCPXML.")
    print(f"Loaded {len(text_pairs)} bilingual pairs (中文+英文) from TXT.")

    # ============================================================
    # 🧠 v3 多轮全局最优匹配（你建议的选最优方案！彻底解决贪心乱序）
    #
    # 老 v1/v2 致命问题（你实锤的）：
    #   Pass1 从左到右贪心 → 只要中间插入 1 条 txt 没有的中文
    #   → 后面某条弱匹配（0.45~0.70 的假高匹配）一把 cursor 拉偏
    #   → 后面所有正常字幕都变成「错位 1/N 条」，全局完全乱序
    #
    # 新 v3 流程：4 轮 + 最后全局 Hungarian DP 兜底
    #   Pass 1: 贪心预对齐（用 v2 的滑窗+cursor 逻辑），给每条 title 打初匹配和分数
    #   Pass 2: 释放所有低自信(<TH_RELEASE=0.65) 的对齐，回到「未匹配」状态
    #   Pass 3: 对剩余未匹配 title + 未匹配 pair 做 ±WINDOW 滑窗
    #           做 1:1 模糊匹配（还是 v3 新算法，不再锁 cursor）
    #   Pass 4: 🧩【核心】对 Pass1~3 后仍在「错位窗口」的 title/pair
    #           收集周围 ±16 范围的所有候选，建 max-weight 二分图
    #           Hungarian DP (bitmask, n<=20) 求全局最优配对
    #           → 总分数最大化，不再会被一条弱匹配拉偏！
    #   最后：剩余的强匹配(>=0.70)就保留下来，其他的全部当插入跳过（保留原中文不加英文）
    # ============================================================
    n_title = len(all_titles)
    n_pair  = len(text_pairs)

    # 结果数组：title_final_match[i] = (pair_j or -1, score, lock_level: 0未匹配/1Pass1/2Pass3/3DP)
    title_final_match = [-1] * n_title
    title_final_score = [0.0] * n_title
    title_final_level = [0] * n_title   # 0未匹配 1Pass1 2Pass3 3HungarianDP
    pair_used = set()

    WINDOW = V48_SEARCH_WINDOW   # 30
    RELEASE_SCORE = 0.65         # Pass2 释放阈值：<0.65 的都视为"可能错"，丢回池中重算
    WEAK_ACCEPT = 0.45
    STRONG_ACCEPT = V48_HIGH_CONFIDENCE  # 0.75
    DP_WINDOW_HALF = 16         # Pass4 DP ±16 范围
    DP_MAX_SIZE = 22            # bitmask DP 最多 22 条 (2^22 ≈ 4M 状态)

    # -----------------------------------------------------------
    # Pass 1: 贪心初对齐（v2 单调 cursor 逻辑），但这次只记录结果不直接写树
    # -----------------------------------------------------------
    print("\n" + "-" * 72)
    print("🧠 v3 Pass 1/4：贪心预对齐（v2 单调 cursor + 滑窗）")
    cursor = 0
    pass1_match = [-1] * n_title
    pass1_score = [0.0] * n_title
    used_p1 = set()
    for ti, title in enumerate(all_titles):
        ot = get_text_from_title(title)
        s_from = max(0, cursor - WINDOW // 3)
        s_to   = min(n_pair, cursor + WINDOW)
        cands = []
        for jj in range(s_from, s_to):
            if jj in used_p1: continue
            sc = get_similarity_v48(ot, text_pairs[jj]["orig"])
            cands.append((sc, jj))
        cands.sort(reverse=True)
        if not cands:
            continue
        best_sc, best_j = cands[0]
        sec_sc = cands[1][0] if len(cands) >= 2 else 0.0
        if best_sc >= STRONG_ACCEPT:
            # 强接受，直接锁 cursor
            pass1_match[ti] = best_j
            pass1_score[ti] = best_sc
            used_p1.add(best_j)
            cursor = max(cursor, best_j + 1)
        elif best_sc >= WEAK_ACCEPT:
            if best_j < cursor - 2:
                continue
            if (best_sc - sec_sc) < 0.10:
                continue   # 歧义不接受
            pass1_match[ti] = best_j
            pass1_score[ti] = best_sc
            used_p1.add(best_j)
            cursor = max(cursor, best_j + 1)
        # else <0.45 跳过
    n_pass1_ok = sum(1 for x in pass1_match if x >= 0)
    print(f"  Pass1 预匹配：{n_pass1_ok}/{n_title} 条 title")
    print("-" * 72)

    # -----------------------------------------------------------
    # Pass 2: 释放所有分数 < RELEASE_SCORE 的配对，把弱匹配全部丢回池中重算
    # -----------------------------------------------------------
    print("\n🧠 v3 Pass 2/4：释放低自信匹配 (<0.65) → 回到未匹配池")
    release_count = 0
    pair_used_pass2 = set()
    for ti in range(n_title):
        pj = pass1_match[ti]
        if pj < 0: continue
        sc = pass1_score[ti]
        if sc < RELEASE_SCORE:
            # 释放：不算匹配
            pass1_match[ti] = -1
            pass1_score[ti] = 0.0
            release_count += 1
        else:
            # 保留：写进 title_final_match，锁死
            title_final_match[ti] = pj
            title_final_score[ti] = sc
            title_final_level[ti] = 1
            pair_used.add(pj)
            pair_used_pass2.add(pj)
    print(f"  Pass2 释放弱匹配：{release_count} 条 → 保留强匹配 = {sum(1 for x in title_final_match if x>=0)} 条")
    print("-" * 72)

    # -----------------------------------------------------------
    # Pass 3: 滑窗二次对齐（未匹配 title ↔ 未用 pair，±WINDOW 滑窗，不再锁 cursor）
    # -----------------------------------------------------------
    print("\n🧠 v3 Pass 3/4：滑窗二次对齐（未匹配 title ↔ 未用 pair，±30 滑窗不再锁 cursor）")
    for ti in range(n_title):
        if title_final_match[ti] >= 0: continue  # 已经锁死
        ot = get_text_from_title(all_titles[ti])
        # 按顺序估算：anchor_j ≈ ti * (n_pair / n_title) 比例估计中心，再 ±WINDOW
        anchor_j = int(round(ti * (n_pair / max(1, n_title))))
        s_from = max(0, anchor_j - WINDOW)
        s_to   = min(n_pair, anchor_j + WINDOW + 1)
        cands = []
        for jj in range(s_from, s_to):
            if jj in pair_used: continue
            sc = get_similarity_v48(ot, text_pairs[jj]["orig"])
            if sc < WEAK_ACCEPT:
                continue
            cands.append((sc, jj))
        cands.sort(reverse=True)
        if not cands: continue
        best_sc, best_j = cands[0]
        sec_sc = cands[1][0] if len(cands) >= 2 else 0.0
        # Pass3 接受阈值：必须 >= 0.50 且 非歧义
        accept_cut = 0.50
        if best_sc >= accept_cut and (len(cands) < 2 or (best_sc - sec_sc) >= 0.08):
            title_final_match[ti] = best_j
            title_final_score[ti] = best_sc
            title_final_level[ti] = 2
            pair_used.add(best_j)
    n_pass3 = sum(1 for x in title_final_level if x == 2)
    print(f"  Pass3 二次命中：{n_pass3} 条 → 当前累计匹配 = {sum(1 for x in title_final_match if x>=0)} 条")
    print("-" * 72)

    # -----------------------------------------------------------
    # Pass 4: 🧩 Hungarian DP (bitmask) 全局最优，兜底所有剩余可能错位的区域
    #
    # 策略：
    #   1. 扫 title 数组，找每个「title 连续未匹配 + pair 连续未使用」的 cluster
    #      （大小 <= DP_MAX_SIZE 就跑 DP）
    #   2. 对 cluster 内的 srt/pair 构建二分图 weight[i][j]
    #      = get_similarity_v48(ti.orig, pj.orig) 若 >= 0.35 否则 0
    #   3. bitmask DP 求全局最大总权重 → 一次性把 cluster 内所有错位重新摆到最优点
    #   4. DP 得分 >= 0.40 的才接受，否则当插入跳过
    # -----------------------------------------------------------
    print("\n🧠 v3 Pass 4/4：🧩 Hungarian bitmask DP 全局最优（小窗口兜底，彻底解决贪心错位）")
    # Step 4.1 枚举未匹配 title 的连续 cluster（间隔 ≤ 4 算同一 cluster，否则断开）
    unvisited_t = [ti for ti in range(n_title) if title_final_match[ti] < 0]
    # Step 4.2 同时找未使用 pair 的 range
    unused_pair_all = sorted([j for j in range(n_pair) if j not in pair_used])
    # 把未匹配的 title 按位置聚类成 cluster（相邻距离 <= 4 合一组）
    clusters = []
    cur_t_list = []
    for i, ti in enumerate(unvisited_t):
        if not cur_t_list:
            cur_t_list = [ti]
        elif ti - cur_t_list[-1] <= 4:
            cur_t_list.append(ti)
        else:
            clusters.append(cur_t_list)
            cur_t_list = [ti]
    if cur_t_list:
        clusters.append(cur_t_list)
    # 对每个 cluster：估算它对应的 pair anchor 区间（根据已匹配点前后插值）
    # 取 cluster 中 min_ti / max_ti，然后拿左右最近匹配的 pair_j 插值得出 pair 区间
    def _estimate_pair_range_for_t_cluster(ts_list):
        lo_t = min(ts_list)
        hi_t = max(ts_list)
        # 左侧最近已匹配
        left_pj = 0
        for xi in range(lo_t - 1, -1, -1):
            if title_final_match[xi] >= 0:
                left_pj = title_final_match[xi] + 1; break
        # 右侧最近已匹配
        right_pj = n_pair - 1
        for xi in range(hi_t + 1, n_title):
            if title_final_match[xi] >= 0:
                right_pj = title_final_match[xi] - 1; break
        return left_pj, right_pj
    dp_hit_total = 0
    for c_idx, tlist in enumerate(clusters):
        if len(tlist) < 1: continue
        p_lo, p_hi = _estimate_pair_range_for_t_cluster(tlist)
        p_lo = max(0, min(n_pair - 1, p_lo))
        p_hi = max(p_lo, min(n_pair - 1, p_hi))
        # 再扩 ±DP_WINDOW_HALF
        p_lo = max(0, p_lo - DP_WINDOW_HALF)
        p_hi = min(n_pair - 1, p_hi + DP_WINDOW_HALF)
        plist_all = [j for j in range(p_lo, p_hi + 1) if j not in pair_used]
        # 过滤最多 DP_MAX_SIZE（title 和 pair 都），超了就砍成两部分
        if len(tlist) > DP_MAX_SIZE or len(plist_all) > DP_MAX_SIZE:
            # cluster 太大，跳过（一般不会发生，因为是连续未匹配小区域）
            print(f"  ⚠️  Cluster {c_idx+1} 过大 (titles={len(tlist)}, pairs={len(plist_all)})，跳过 DP")
            continue
        LS = len(tlist)
        LP = len(plist_all)
        # 如果有一个为 0，跳过
        if LS == 0 or LP == 0: continue
        # Build weight matrix LS × LP
        W = [[0.0] * LP for _ in range(LS)]
        for i2 in range(LS):
            ti = tlist[i2]
            ot = get_text_from_title(all_titles[ti])
            for j2 in range(LP):
                pj = plist_all[j2]
                sc = get_similarity_v48(ot, text_pairs[pj]["orig"])
                if sc >= 0.35:
                    W[i2][j2] = sc
                else:
                    W[i2][j2] = 0.0
        # DP bitmask 只覆盖 pair 侧 bitmask（因为 pair 一般少一些，或取小的一侧 mask）
        # 我们选 min 侧做 bitmask
        transpose = False
        if LP <= LS:
            mask_side = LP   # pair 侧作为 bitmask（每个 pair 用 1 bit）
        else:
            mask_side = LS
            transpose = True
        if mask_side > DP_MAX_SIZE:
            continue  # 超过 22 bits 就不跑了
        FULL = (1 << mask_side) - 1
        from collections import defaultdict
        dp = {}
        dp[(0, 0)] = (0.0, None, None)   # (i_next or j_next, used_mask) = (best_score, prev_state, choice)
        # state = (k, used_mask) where k = next index on the "major side" to assign
        # Standard DP: iterate k (major side index from 0..major_len-1), try all l ∈ minor
        if not transpose:
            MAJOR, MINOR = LS, LP
        else:
            MAJOR, MINOR = LP, LS
        dp = {}
        start_st = (0, 0)
        dp[start_st] = (0.0, None, None)  # state = (next_major_idx, minor_used_mask) → (score, prev_st, (maj_i, min_j))
        for (k, mask) in list(dp.keys()):
            if k >= MAJOR:
                continue
            cur_score = dp[(k, mask)][0]
            # Option A: skip this major index (score + 0)
            st_A = (k + 1, mask)
            if st_A not in dp or dp[st_A][0] < cur_score:
                dp[st_A] = (cur_score, (k, mask), None)
            # Option B: match major[k] to any unused minor index l (add W[...] if matches)
            for l in range(MINOR):
                if (mask >> l) & 1:
                    continue
                if not transpose:
                    w = W[k][l]
                else:
                    w = W[l][k]
                if w <= 0.0:
                    continue  # 相似度太低就不匹配，省掉坏的连接
                new_mask = mask | (1 << l)
                new_score = cur_score + w
                st_B = (k + 1, new_mask)
                if st_B not in dp or dp[st_B][0] < new_score:
                    dp[st_B] = (new_score, (k, mask), (k, l))
        # 找到终止态最好的：(MAJOR, any mask)
        best_end = None
        best_end_score = -1e9
        for (kk, mm), (sc, _, _) in dp.items():
            if kk == MAJOR and sc > best_end_score:
                best_end_score = sc
                best_end = (kk, mm)
        if best_end is None:
            continue
        # Backtrack: 找到所有 (maj_i, min_j) 的组合
        matches_in_cluster = []   # (tlist_i, plist_j, score)
        cur_st = best_end
        while True:
            _, prev_st, choice = dp[cur_st]
            if choice is not None:
                kk, ll = choice
                if not transpose:
                    ti_idx, pj_idx = kk, ll
                else:
                    ti_idx, pj_idx = ll, kk
                if 0 <= ti_idx < LS and 0 <= pj_idx < LP:
                    sc = W[ti_idx][pj_idx]
                    if sc >= 0.40:   # 接受阈值
                        matches_in_cluster.append((ti_idx, pj_idx, sc))
            if prev_st is None:
                break
            cur_st = prev_st
        # 应用结果到 title_final_match + pair_used
        hit_this = 0
        for (ti_idx, pj_idx, sc) in matches_in_cluster:
            ti_real = tlist[ti_idx]
            pj_real = plist_all[pj_idx]
            if pj_real in pair_used:
                continue
            if title_final_match[ti_real] >= 0:
                continue
            title_final_match[ti_real] = pj_real
            title_final_score[ti_real] = sc
            title_final_level[ti_real] = 3
            pair_used.add(pj_real)
            hit_this += 1
        dp_hit_total += hit_this
        print(f"  Cluster {c_idx+1}: titles {len(tlist)}条 / pairs ~{len(plist_all)}条 → Hungarian 命中 {hit_this} 条")
    print(f"  Pass4 Hungarian DP 总命中：{dp_hit_total} 条")
    print("-" * 72)

    # -----------------------------------------------------------
    # Final: 现在 title_final_match 里就是全局最优匹配了
    #        遍历应用：命中的替换中文+加英文；未命中的保留原中文（不加英文，记为插入）
    # -----------------------------------------------------------
    matched_count   = 0
    skipped_insert  = 0
    ambiguous_skip  = 0

    for title_idx in range(n_title):
        title = all_titles[title_idx]
        best_j = title_final_match[title_idx]
        best_sc = title_final_score[title_idx]
        lock_lv = title_final_level[title_idx]

        if best_j < 0:
            # 未匹配：判定为插入字幕/txt没有，跳过
            skipped_insert += 1
            if title_idx < 60 or skipped_insert <= 10:
                ot = get_text_from_title(title)
                print(f"  ⏭  [{title_idx+1}/{n_title}] SKIP: {ot[:28]}… sc=无匹配 (未匹配插入)")
            continue

        best_pair = text_pairs[best_j]
        matched_count += 1
        level_name = {1:"P1-STRONG", 2:"P3-SLIDE", 3:"P4-HUNG"}.get(lock_lv, "OK")
        if title_idx < 60 or matched_count <= 20:
            ot = get_text_from_title(title)
            print(f"  ✅ [{title_idx+1}/{n_title}] {level_name:8s} ({best_sc:.3f}): {ot[:32]}… → pair[{best_j+1}] {best_pair['orig'][:28]}…")
        elif matched_count == 21:
            print(f"  …（后面 {n_title-60} 条简略，不再逐行打印，总计 matched_count 看结尾）…")

        # 1. Update Original Text (with corrections from TXT)
        set_text_to_title(title, best_pair["orig"])

        # 2. Create Translation Title (Clone)
        en_title = copy.deepcopy(title)

        # Update Translation Title Properties
        set_text_to_title(en_title, best_pair["trans"])

        # Lane: +1
        # We explicitly set original to lane 1 and translation to lane 2
        # to avoid stacking into higher lanes which might have pre-set offsets.
        title.set("lane", "1")
        en_title.set("lane", "2")

        # Role
        en_title.set("role", "EN.EN-1")

        # Position: Force absolute values
        # First line (original) to -450
        # Second line (translation) to -502
        update_position(title, -450)
        update_position(en_title, -502)

        # Font Size: Smaller
        update_font_size(en_title, 0.66)

        id_map = {}
        # 1. Collect and remap all IDs within the cloned title
        for elem in en_title.iter():
            eid = elem.get("id")
            if eid:
                new_eid = f"{eid}_en_{matched_count}"
                id_map[eid] = new_eid
                elem.set("id", new_eid)

        # 2. Update all references within the cloned title to point to the new IDs
        for elem in en_title.iter():
            # Check 'ref' attribute (used by text-style)
            ref = elem.get("ref")
            if ref and ref in id_map:
                elem.set("ref", id_map[ref])

            # Some FCPXML versions might use other reference attributes
            # but 'ref' is the most common for style definitions.

        # Insert into Parent
        # We need the parent of the original title
        parent = parent_map.get(title)
        if parent is not None:
            children = list(parent)
            idx = children.index(title)
            parent.insert(idx + 1, en_title)

    # --- 最终统计 ---
    total_title = n_title
    print()
    print("=" * 72)
    print(f"🧮 add_bilingual_subs v3 多轮全局最优匹配统计：")
    print(f"  总字幕数（时间线 title）  = {total_title}")
    print(f"  TXT 双语对总数            = {n_pair}")
    print(f"  ✅ 命中+加英文           = {matched_count}")
    lv1 = sum(1 for x in title_final_level if x == 1)
    lv2 = sum(1 for x in title_final_level if x == 2)
    lv3 = sum(1 for x in title_final_level if x == 3)
    print(f"     · Pass1 强命中(>=0.65)= {lv1}")
    print(f"     · Pass3 滑窗二次命中  = {lv2}")
    print(f"     · 🧩 Pass4 Hungarian全局最优= {lv3}")
    print(f"  ⏭  跳过（插入新字幕/txt没）= {skipped_insert}")
    print(f"  TXT 已使用率              = {len(pair_used)}/{n_pair}")
    print("-" * 72)
    if len(pair_used) < n_pair:
        unused = sorted([j for j in range(n_pair) if j not in pair_used])
        show_n = min(8, len(unused))
        print(f"  ⚠️  TXT 里剩余 {len(unused)} 条对没对应上（时间线可能缺了对应字幕位置）→ 前 {show_n} 条 pair 编号：{[j+1 for j in unused[:show_n]]}")
    if skipped_insert > 0:
        print(f"  💡 跳过的字幕：保留原中文，没加英文，不污染后续对齐（Hungarian全局最优保证了）")
    print("=" * 72)
    tree.write(output_path, encoding="UTF-8", xml_declaration=True)

if __name__ == "__main__":
    print("\n" + "="*55)
    print("        FCPXML Subtitle Assistant        ")
    print("="*55)
    print("1. Extract Subtitles -> TXT")
    print("   [Description]: Extracts all subtitles from an FCPXML timeline into a plain text file.")
    print("   Useful for proofreading or preparing a translation blueprint.")
    print("   Output: A text file with one subtitle per line (no timecode).")
    print()
    print("2. Generate New Bilingual Timeline (SRT + TXT -> FCPXML)")
    print("   [Description]: Creates a BRAND NEW FCPXML timeline purely from subtitles.")
    print("   - Uses SRT for TIMECODE (when each line appears) and sentence breaks.")
    print("   - Uses TXT for CORRECT TEXT (ignores SRT typos from auto-captions).")
    print("   - Matches SRT lines to TXT bilingual pairs via v48 fuzzy matching.")
    print("   - Chinese lane 1 (Y=-450), English lane 2 (Y=-502), scaled font.")
    print()
    print("3. Add Bilingual Subtitles (FCPXML + TXT -> FCPXML)")
    print("   [Description]: Updates an EXISTING FCPXML timeline with bilingual subtitles.")
    print("   - Replaces original Chinese subtitles with corrected text from your TXT.")
    print("   - Adds a new English subtitle line below the Chinese one.")
    print("   - Automatically adjusts font size and position.")
    print("="*55)

    choice = input("\nEnter choice (1 / 2 / 3): ").strip()

    if choice == "1":
        print("\n--- Step 1: Select Input FCPXML ---")
        xml_input = select_file_from_list(['.fcpxml', '.fcpxmld'], "Enter file number or path: ")

        if not xml_input:
             print("No file selected.")
             sys.exit(1)

        print("\n--- Step 2: Output TXT Path ---")
        base_name = os.path.splitext(os.path.basename(xml_input))[0]
        default_output = f"{base_name}_subs.txt"

        txt_output = input(f"Enter path to output TXT file [Default: {default_output}]: ").strip()
        txt_output = txt_output.replace('"', '').replace("'", "")
        if not txt_output:
            txt_output = default_output
        elif os.path.isdir(txt_output):
            txt_output = os.path.join(txt_output, default_output)

        if not os.path.exists(xml_input) and not xml_input.endswith(".fcpxmld"):
             print(f"Error: {xml_input} not found.")
             sys.exit(1)

        extract_subtitles_to_txt(xml_input, txt_output)

    elif choice == "2":
        print("\n" + "-" * 55)
        print("  Mode 2: SRT (Timing) + TXT (Correct Text) -> FCPXML")
        print("-" * 55)

        print("\n--- Step 1: Select SRT File (provides timecode & sentence breaks) ---")
        srt_input = select_file_from_list(['.srt'], "Enter file number or path: ")
        srt_input = srt_input.strip()
        if not srt_input:
             print("No SRT file selected.")
             sys.exit(1)
        if not os.path.exists(srt_input):
            print(f"Error: SRT file not found -> {srt_input}")
            sys.exit(1)

        print("\n--- Step 2: Select TXT File (provides correct text) ---")
        print("   Format options:")
        print("     - MONO (每行中文/原文，无译文）")
        print("     - BILINGUAL (奇数行原文 + 偶数行译文，空行分隔段落）")
        text_input = select_file_from_list(['.txt', '.rtf', '.doc', '.docx'], "Enter file number or path: ")
        text_input = text_input.strip()
        if not text_input:
             print("No TXT file selected.")
             sys.exit(1)
        if not os.path.exists(text_input):
            print(f"Error: TXT file not found -> {text_input}")
            sys.exit(1)

        txt_mode = "auto"
        # (Mode selection is always auto — the three-mode choice was removed per
        #  user request since auto correctly detects bilingual vs. monolingual
        #  in all practical cases, saving one prompt.)

        print("\n--- Step 3: Timeline FPS ---")
        print("  Presets:  [1] 23.976  [2] 24 (Default)  [3] 25  [4] 29.97  [5] 30  [6] 50  [7] 60")
        fps_str = input("  Enter preset number (1-7), or a custom number, or press ENTER for 24: ").strip()
        fps = 24
        if fps_str:
            presets = {"1": 23.976, "2": 24, "3": 25, "4": 29.97, "5": 30, "6": 50, "7": 60}
            if fps_str in presets:
                fps = presets[fps_str]
            else:
                try:
                    fps = float(fps_str)
                except:
                    fps = 24
        if fps < 1: fps = 24
        print(f"  Using FPS = {fps}")

        auto_zero_tc = True
        granularity_align = True
        # (Both switches removed from interactive prompt per user request;
        #  they default to ON which is the correct behavior for 99% of cases.
        #  TC zeroing uses a smart floor-hour heuristic, see Step A implementation.)

        print("\n--- Step 4: Output FCPXML Path ---")
        srt_base = os.path.splitext(os.path.basename(srt_input))[0]
        default_output = f"{srt_base}_bilingual.fcpxml"
        xml_output = input(f"Enter path to output FCPXML file [Default: {default_output}]: ").strip()
        xml_output = xml_output.replace('"', '').replace("'", "")
        if not xml_output:
            xml_output = default_output
        elif os.path.isdir(xml_output):
            xml_output = os.path.join(xml_output, default_output)

        print("\n[INFO] Parsing SRT ...")
        srt_entries = parse_srt(srt_input)
        if not srt_entries:
            print("[ERROR] Failed to parse any entries from SRT.")
            sys.exit(1)

        print(f"\n[INFO] Parsing TXT ... (mode={txt_mode})")
        pairs = parse_bilingual_text(text_input, mode=txt_mode)
        print(f"[INFO] Loaded {len(pairs)} text items from TXT.")
        if not pairs:
            print("[ERROR] No text items loaded from TXT. Abort.")
            sys.exit(1)

        engine_tag = "v48 + local-window + pinyin-fallback + TC-zero + granularity-bridge" if granularity_align else "v48 + local-window + pinyin-fallback"
        print(f"\n[INFO] Matching {len(srt_entries)} SRT entries -> {len(pairs)} TXT items  (engine: {engine_tag}) ...")
        result = generate_fcpxml_from_srt_and_txt(srt_entries, pairs, xml_output,
                                                  fps=fps, auto_zero_tc=auto_zero_tc,
                                                  granularity_align=granularity_align)
        ok = result[0] if isinstance(result, tuple) else result
        if ok:

            print(f"\n✅ Output written to (absolute path): {os.path.abspath(xml_output)}")
            print("   You can now import this .fcpxml directly into Final Cut Pro.")
        else:
            print("\n❌ Generation failed (see messages above).")
            sys.exit(1)

    elif choice == "3":
        print("\n--- Step 1: Select Input FCPXML ---")
        xml_input = select_file_from_list(['.fcpxml', '.fcpxmld'], "Enter file number or path: ")

        if not xml_input:
             print("No file selected.")
             sys.exit(1)

        print("\n--- Step 2: Select Bilingual Text File ---")
        text_input = select_file_from_list(['.txt', '.rtf', '.doc', '.docx'], "Enter file number or path: ")

        if not text_input:
             print("No file selected.")
             sys.exit(1)

        print("\n--- Step 3: Output FCPXML Path ---")
        base_name = os.path.splitext(os.path.basename(xml_input))[0]
        default_output = f"{base_name}_bilingual.fcpxml"

        xml_output = input(f"Enter path to output FCPXML file [Default: {default_output}]: ").strip()
        xml_output = xml_output.replace('"', '').replace("'", "")
        if not xml_output:
            xml_output = default_output
        elif os.path.isdir(xml_output):
            xml_output = os.path.join(xml_output, default_output)

        if not os.path.exists(xml_input) and not xml_input.endswith(".fcpxmld"):
            print(f"Error: {xml_input} not found.")
            sys.exit(1)

        if not os.path.exists(text_input):
            print(f"Error: {text_input} not found.")
            sys.exit(1)

        pairs = parse_bilingual_text(text_input)
        print(f"Loaded {len(pairs)} bilingual pairs from text file.")

        add_bilingual_subs(xml_input, pairs, xml_output)
        print(f"\nOutput written to (absolute path): {os.path.abspath(xml_output)}")
    else:
        print("Invalid choice.")
