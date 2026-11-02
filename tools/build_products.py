#!/usr/bin/env python3
"""从 Open Food Facts 的 Parquet 导出筛出瑞典、丹麦、芬兰在售且录了配料的商品，生成 App 打包和每周更新用的离线商品库。

数据：Open Food Facts（https://world.openfoodfacts.org），ODbL 1.0 许可。生成的商品库同样以 ODbL 1.0 公开。
本脚本：PolyForm Noncommercial License 1.0.0（tools/LICENSE），不允许商用。
Required Notice: Copyright kesar (https://github.com/ClaymanTwinkle)

先下载 Hugging Face 上的 food.parquet（约 8 GB，全球商品），再用 DuckDB 筛。
不要用 DuckDB 直接远程按列读：会发几千个范围请求，被 Hugging Face 按 IP 限流（429）。

输出（--out 目录）：
  products.json.zlib   商品库：JSON 用 zlib 原始 deflate 压缩（App 用 NSData.decompressed(using: .zlib) 解开）
  manifest.json        版本（生成日期）、商品数、products.json.zlib 的 SHA-256 和字节数

商品库 JSON：{"version": "2026-11-02", "license": ..., "products": {条码: [名称, 规格, 品牌, 正面图路径, {语言: 配料}]}}
  - 配料只留 sv、da、fi、en 和商品主语言那一栏（主语言记作 "main"，和前面某种重复时不存）
  - 正面图路径是 images.openfoodfacts.org/images/products/ 后面那段，没有就是空字符串

用法：
  python3 -m venv /tmp/offdb/venv && /tmp/offdb/venv/bin/pip install duckdb
  curl -L -C - -o /tmp/offdb/food.parquet https://huggingface.co/datasets/openfoodfacts/product-database/resolve/main/food.parquet
  /tmp/offdb/venv/bin/python -I tools/build_products.py --parquet /tmp/offdb/food.parquet --out <输出目录>
"""
import argparse, datetime, hashlib, json, os, re, zlib

COUNTRIES = ['en:sweden', 'en:denmark', 'en:finland']
LANGUAGES = ['sv', 'da', 'fi', 'en']
LICENSE = ('Contains information from Open Food Facts (https://world.openfoodfacts.org), '
           'made available under the Open Database License (ODbL) 1.0: https://opendatacommons.org/licenses/odbl/1-0/')


def fetch(parquet, cache):
    import duckdb
    c = duckdb.connect()
    if not os.path.exists(cache):
        countries = ' OR '.join(f"list_contains(countries_tags, '{x}')" for x in COUNTRIES)
        c.execute(f"""COPY (
            SELECT code, product_name, brands, quantity, ingredients_text, lang,
                   list_transform(list_filter(images, lambda i: i.key LIKE 'front_%'),
                                  lambda i: struct_pack(k := i.key, r := i.rev)) AS fronts
            FROM '{parquet}'
            WHERE ({countries}) AND coalesce(obsolete, false) = false
              AND len(list_filter(ingredients_text, lambda t: length(trim(coalesce(t.text, ''))) > 0)) > 0
        ) TO '{cache}' (FORMAT parquet)""")
    return c.execute(f"SELECT code, product_name, brands, quantity, ingredients_text, lang, fronts FROM '{cache}'").fetchall()


def image_path(code, fronts, lang):
    """front_sv.12 → 731/222/201/1430/front_sv.12.200.jpg；8 位以下的条码不分段。"""
    if not fronts:
        return ''
    by_key = {f['k']: f['r'] for f in fronts if f['r'] is not None}
    for key in [f'front_{lang}', *(f'front_{l}' for l in LANGUAGES), *sorted(by_key)]:
        if key in by_key:
            padded = code.zfill(13) if len(code) > 8 else code
            folder = '/'.join([padded[0:3], padded[3:6], padded[6:9], padded[9:]]) if len(padded) > 8 else padded
            return f'{folder}/{key}.{by_key[key]}.200.jpg'
    return ''


def clean(text):
    """去掉 Open Food Facts 标过敏原用的 <span class="allergen">…</span> 和 _Vetemjöl_、vete_mjöl，和 App 里 OfflineProduct.cleanIngredients 一致。"""
    text = re.sub(r'<[^>]+>', '', text)
    text = text.replace('_', '')  # 合成词里标一半的也有：vete_mjöl、skum_mjölk
    return re.sub(r'\s+', ' ', text).strip()


def localized(entries, lang, cleaner=lambda t: t.strip()):
    texts = {e['lang']: cleaner(e['text']) for e in entries or [] if e['text'] and e['text'].strip()}
    texts = {k: v for k, v in texts.items() if v}
    return texts, texts.get('main') or texts.get(lang)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--parquet', required=True, help='下载好的 food.parquet')
    parser.add_argument('--out', required=True)
    parser.add_argument('--cache', default='/tmp/offdb/nordic.parquet', help='筛出来的中间文件，存在就不重新拉')
    args = parser.parse_args()

    products = {}
    for code, names, brands, quantity, ingredients, lang, fronts in fetch(args.parquet, args.cache):
        if not code or not code.isdigit():
            continue
        texts, main_text = localized(ingredients, lang, clean)
        kept = {l: texts[l] for l in LANGUAGES if l in texts}
        if main_text and main_text not in kept.values():
            kept['main'] = main_text
        if not kept:
            continue
        name_texts, main_name = localized(names, lang)
        name = next((name_texts[l] for l in LANGUAGES if l in name_texts), main_name or '')
        brand = (brands or '').split(',')[0].strip()
        products[code] = [name, (quantity or '').strip(), brand, image_path(code, fronts, lang), kept]

    version = datetime.date.today().isoformat()
    doc = {'version': version, 'license': LICENSE, 'products': dict(sorted(products.items()))}
    raw = json.dumps(doc, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    compressor = zlib.compressobj(9, zlib.DEFLATED, -15)  # 原始 deflate，不带 zlib 头，和苹果 COMPRESSION_ZLIB 一致
    packed = compressor.compress(raw) + compressor.flush()

    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, 'products.json.zlib'), 'wb') as f:
        f.write(packed)
    manifest = {'version': version, 'count': len(products), 'bytes': len(packed),
                'sha256': hashlib.sha256(packed).hexdigest(), 'license': LICENSE}
    with open(os.path.join(args.out, 'manifest.json'), 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    print(f'{len(products)} 件商品，JSON {len(raw) / 1e6:.1f} MB，压缩后 {len(packed) / 1e6:.1f} MB')


if __name__ == '__main__':
    main()
