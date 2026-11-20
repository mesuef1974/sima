from sima.services import raster


def _bar(size: int, x0: int, w: int) -> list[list[int]]:
    return [[0 if x0 <= x < x0 + w else 255 for x in range(size)] for _ in range(size)]


def test_threshold_and_coverage():
    g = _bar(16, 4, 4)
    m = raster.threshold(g)
    assert raster.coverage(m) == 4 / 16


def test_min_thickness_of_vertical_bar():
    m = raster.threshold(_bar(32, 10, 5))
    assert 4.5 <= raster.min_thickness(m) <= 5.5
    m1 = raster.threshold(_bar(32, 10, 3))
    assert raster.min_thickness(m1) <= 3.6


def test_thickness_takes_thin_feature_into_account():
    # عمود سميك 8 وشعرة سماكة 1: المئين الخامس يلتقط الشعرة
    g = [[255] * 64 for _ in range(64)]
    for y in range(64):
        for x in range(8, 16):
            g[y][x] = 0
        for x in range(40, 43):
            g[y][x] = 0
    m = raster.threshold(g)
    assert raster.min_thickness(m) <= 3.6


def test_triangle_tips_are_not_strokes():
    tri = [[0 if (x >= 10 and y >= 10 and x + y <= 100) else 255 for x in range(128)] for y in range(128)]
    assert raster.min_thickness(raster.threshold(tri)) >= 10  # رؤوس المثلث لا تُحسب ضربات؛ القياس يبقى تقريبيًا عند الرؤوس


def test_square_corners_do_not_drag_thickness_down():
    # مربع 40×40: السماكة المحلية في كل مكان قريبة من 40 إلا شظايا الزوايا
    g = [[0 if 10 <= x < 50 and 10 <= y < 50 else 255 for x in range(64)] for y in range(64)]
    assert raster.min_thickness(raster.threshold(g)) >= 30


def test_euclidean_distance_is_exact_for_disc_center():
    g = [[255] * 41 for _ in range(41)]
    for y in range(41):
        for x in range(41):
            if (x - 20) ** 2 + (y - 20) ** 2 <= 100:
                g[y][x] = 0
    d2 = raster.euclidean_distance_sq(raster.threshold(g))
    assert 90 <= d2[20][20] <= 121


def test_components():
    g = [[255] * 16 for _ in range(16)]
    for y in range(2, 6):
        for x in range(2, 6):
            g[y][x] = 0
    for y in range(10, 14):
        for x in range(10, 14):
            g[y][x] = 0
    assert raster.components(raster.threshold(g)) == 2


def test_hashes_deterministic_and_discriminative():
    a = _bar(32, 0, 16)
    b = raster.invert(a)
    c = [[0 if (x // 4 + y // 4) % 2 == 0 else 255 for x in range(32)] for y in range(32)]
    assert raster.dhash(a) == raster.dhash(a)
    assert raster.phash(a) == raster.phash(a)
    assert raster.hamming(raster.dhash(a), raster.dhash(a)) == 0
    assert raster.hamming(raster.phash(a), raster.phash(b)) > 10
    assert raster.hamming(raster.phash(a), raster.phash(c)) > 10
    assert len(raster.dhash(a)) == 16


def test_resample_box_average():
    g = [[0, 255], [255, 0]]
    assert raster.resample(g, 1, 1) == [[127]]


def test_bbox():
    g = [[255] * 8 for _ in range(8)]
    g[2][3] = 0
    g[5][6] = 0
    assert raster.bbox(raster.threshold(g)) == (3, 2, 6, 5)
    assert raster.bbox(raster.threshold([[255] * 4 for _ in range(4)])) is None
