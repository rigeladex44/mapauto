import io
import time
import random
import logging
import urllib.request
from PIL import Image
from modules.config import SCRIPT_DIR

# Import OpenCV (opsional, fallback jika tidak tersedia)
try:
    import cv2
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False
    logging.warning("⚠️ OpenCV tidak tersedia, akan menggunakan metode PIL saja")

def get_full_captcha_screenshot(page):
    """Ambil screenshot full captcha container"""
    try:
        captcha_container = page.locator(".rc-slider-captcha").first
        if captcha_container.is_visible(timeout=1000):
            screenshot_bytes = captcha_container.screenshot()
            if screenshot_bytes:
                img = Image.open(io.BytesIO(screenshot_bytes))
                return img
        return None
    except Exception as e:
        logging.debug(f"Gagal ambil screenshot full captcha: {e}")
        return None

def detect_piece_first(page):
    """Deteksi piece pertama (moving piece) - di kiri, menggunakan DOM saja"""
    try:
        puzzle_element = page.locator("img.rc-slider-captcha-jigsaw-puzzle").first
        if puzzle_element.is_visible(timeout=1000):
            box = puzzle_element.bounding_box()
            if box:
                captcha_container = page.locator(".rc-slider-captcha").first
                container_box = captcha_container.bounding_box()
                if container_box:
                    offset_x = box['x'] - container_box['x']
                    offset_y = box['y'] - container_box['y']
                    result = {
                        'x': int(offset_x), 'y': int(offset_y),
                        'width': int(box['width']), 'height': int(box['height']),
                        'center_x': offset_x + box['width'] / 2,
                        'center_y': offset_y + box['height'] / 2
                    }
                    logging.info(f"   ✅ Piece pertama ditemukan (DOM): center=({result['center_x']:.1f}, {result['center_y']:.1f}), size={result['width']}x{result['height']}")
                    return result
        logging.warning("   ⚠️ Piece pertama tidak ditemukan di DOM")
        return None
    except Exception as e:
        logging.warning(f"   ⚠️ Error detect_piece_first: {e}")
        return None

def detect_piece_second(page, piece_first_box):
    """Deteksi piece kedua (Target) menggunakan OpenCV"""
    if not piece_first_box or not OPENCV_AVAILABLE:
        return None
    try:
        logging.info("   🔍 STEP 2.1: Mengambil gambar...")
        captcha_container = page.locator(".rc-slider-captcha").first
        bg_element = page.locator(".rc-slider-captcha-jigsaw-bg").first
        piece_element = page.locator(".rc-slider-captcha-jigsaw-puzzle").first
        
        if not bg_element.is_visible(): return None
        
        container_box = captcha_container.bounding_box()
        bg_box = bg_element.bounding_box()
        if not container_box or not bg_box: return None
        
        bg_offset_x = bg_box['x'] - container_box['x']
        bg_offset_y = bg_box['y'] - container_box['y']
        
        bg_url = bg_element.get_attribute("src")
        piece_url = piece_element.get_attribute("src")
        
        logging.info("   📥 Download gambar...")
        temp_bg_path = str(SCRIPT_DIR / "temp_bg.jpg")
        temp_piece_path = str(SCRIPT_DIR / "temp_piece.png")
        urllib.request.urlretrieve(bg_url, temp_bg_path)
        urllib.request.urlretrieve(piece_url, temp_piece_path)
        
        bg_img = cv2.imread(temp_bg_path)
        piece_img = cv2.imread(temp_piece_path)
        if bg_img is None or piece_img is None: return None
        
        bg_height, bg_width = bg_img.shape[:2]
        piece_height, piece_width = piece_img.shape[:2]
        
        piece_gray = cv2.cvtColor(piece_img, cv2.COLOR_BGR2GRAY)
        _, piece_binary = cv2.threshold(piece_gray, 1, 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(piece_binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours: return None
        
        largest_contour = max(contours, key=cv2.contourArea)
        piece_mask = piece_binary.copy()
        
        rendered_width = bg_box['width']
        natural_width = bg_width
        scale_ratio = natural_width / rendered_width
        
        piece_first_x_relative_to_bg = piece_first_box['x'] - bg_offset_x
        piece_first_y_relative_to_bg = piece_first_box['y'] - bg_offset_y
        safe_zone_x_bg = piece_first_x_relative_to_bg + piece_first_box['width'] + 20
        safe_zone_x_cv = int(safe_zone_x_bg * scale_ratio)
        safe_zone_x_cv = max(0, min(safe_zone_x_cv, bg_width - piece_width))
        
        bg_gray = cv2.cvtColor(bg_img, cv2.COLOR_BGR2GRAY)
        bg_edge = cv2.Canny(bg_gray, 50, 150)
        piece_edge = cv2.Canny(piece_gray, 50, 150)
        res_edge = cv2.matchTemplate(bg_edge, piece_edge, cv2.TM_CCOEFF_NORMED)
        res_edge[:, :safe_zone_x_cv] = 0
        
        res_gray = cv2.matchTemplate(bg_gray, piece_gray, cv2.TM_CCOEFF_NORMED)
        res_gray[:, :safe_zone_x_cv] = 0
        
        piece_masked = cv2.bitwise_and(piece_img, piece_img, mask=piece_mask)
        res_masked = cv2.matchTemplate(bg_img, piece_masked, cv2.TM_CCOEFF_NORMED)
        res_masked[:, :safe_zone_x_cv] = 0
        
        results = []
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res_edge)
        results.append({'method': 'edge', 'value': max_val, 'loc': max_loc, 'x_cv': max_loc[0], 'y_cv': max_loc[1]})
        
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res_gray)
        results.append({'method': 'grayscale', 'value': max_val, 'loc': max_loc, 'x_cv': max_loc[0], 'y_cv': max_loc[1]})
        
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res_masked)
        results.append({'method': 'masked', 'value': max_val, 'loc': max_loc, 'x_cv': max_loc[0], 'y_cv': max_loc[1]})
        
        if not results: return None
        best_result = max(results, key=lambda x: x['value'])
        logging.info(f"   🎯 Metode terbaik: {best_result['method']} dengan match={best_result['value']:.3f}")
        
        target_x_cv = best_result['x_cv']
        target_y_cv = best_result['y_cv']
        target_x_bg = target_x_cv / scale_ratio
        target_y_bg = target_y_cv / scale_ratio
        
        if target_x_bg <= piece_first_x_relative_to_bg + piece_first_box['width']: return None
        y_diff = abs(target_y_bg - piece_first_y_relative_to_bg)
        if y_diff > 50: return None
        if target_x_cv + piece_width > bg_width or target_y_cv + piece_height > bg_height: return None
        
        final_x = target_x_bg + bg_offset_x
        final_y = target_y_bg + bg_offset_y
        final_x = max(0, min(final_x, container_box['width'] - piece_first_box['width']))
        final_y = max(0, min(final_y, container_box['height'] - piece_first_box['height']))
        
        result = {
            'x': int(final_x), 'y': int(final_y),
            'width': piece_first_box['width'], 'height': piece_first_box['height'],
            'center_x': final_x + (piece_first_box['width'] / 2),
            'center_y': final_y + (piece_first_box['height'] / 2)
        }
        logging.info(f"   ✅✅✅ Piece kedua ditemukan: center=({result['center_x']:.1f}, {result['center_y']:.1f})")
        return result
    except Exception as e:
        logging.warning(f"   ⚠️ Error detect_piece_second: {e}")
        return None

def check_pieces_overlap(page, piece_first_box, piece_second_box):
    """Cek apakah kedua piece sudah ketumpuk"""
    try:
        if not piece_first_box or not piece_second_box: return False
        current_piece_first = detect_piece_first(page)
        if not current_piece_first: return False
        
        distance_x = piece_second_box['center_x'] - current_piece_first['center_x']
        distance_y = abs(current_piece_first['center_y'] - piece_second_box['center_y'])
        is_overlap = abs(distance_x) < 3.0 and distance_y < 3.0
        
        if is_overlap:
            logging.info(f"   ✅✅✅ TITIK MERAH DAN KUNING SUDAH MENYATU! X={distance_x:.2f}px, Y={distance_y:.2f}px")
        return is_overlap
    except: return False

def handle_captcha_slider(page):
    """Menangani captcha slider"""
    try:
        if not OPENCV_AVAILABLE:
            logging.error("❌ OpenCV tidak tersedia! Install: python3.11 -m pip install opencv-python")
            return False
        
        page.mouse.up()
        time.sleep(0.1)
        
        logging.info("🔍 STEP 1: Mencari piece pertama...")
        piece_first = detect_piece_first(page)
        if not piece_first: return False
        
        logging.info("🔍 STEP 2: Mencari piece kedua...")
        piece_second = detect_piece_second(page, piece_first)
        if not piece_second: return False
        
        target_distance = piece_second['center_x'] - piece_first['center_x']
        logging.info(f"📍 Target: geser {target_distance:.1f}px")
        
        slider = page.locator(".rc-slider-captcha-button").first
        if not slider.is_visible(timeout=2000): return False
        
        box = slider.bounding_box()
        if not box: return False
        
        start_x = box['x'] + box['width'] / 2
        start_y = box['y'] + box['height'] / 2
        target_x = start_x + target_distance
        
        page.mouse.move(start_x, start_y)
        time.sleep(0.2)
        page.mouse.down()
        time.sleep(0.2)
        
        num_waypoints = max(5, int(target_distance / 30))
        for i in range(num_waypoints + 1):
            t = i / num_waypoints
            eased_t = 1 - (1 - t) ** 3
            y_variation = random.uniform(-2, 2) * (1 - abs(t - 0.5) * 2)
            wx = start_x + (target_x - start_x) * eased_t
            wy = start_y + y_variation
            if i > 0:
                page.mouse.move(wx, wy, steps=random.randint(2, 4))
                delay = random.uniform(0.05, 0.12)
                time.sleep(delay)
        
        page.mouse.move(target_x, start_y, steps=2)
        time.sleep(0.2)
        
        for fine_tune_attempt in range(10):
            is_overlap = check_pieces_overlap(page, piece_first, piece_second)
            if is_overlap: break
            
            current_piece_first = detect_piece_first(page)
            if current_piece_first:
                distance_x = piece_second['center_x'] - current_piece_first['center_x']
                if distance_x > 2:
                    fine_tune_distance = min(distance_x, 6)
                    new_mouse_x = target_x + (fine_tune_attempt * 3) + fine_tune_distance
                    page.mouse.move(new_mouse_x, start_y, steps=2)
                    time.sleep(0.15)
                else: break
            else: break
        
        for i in range(10):
            page.mouse.up()
            time.sleep(0.01)
        
        time.sleep(2)
        captcha_container = page.locator(".rc-slider-captcha").first
        if not captcha_container.is_visible(timeout=500):
            logging.info("  ✅✅✅ CAPTCHA BERHASIL!")
            return True
        return False
    except Exception as e:
        logging.error(f"❌ Error handle captcha: {e}")
        for i in range(5):
            try: page.mouse.up(); time.sleep(0.05)
            except: pass
        return False
