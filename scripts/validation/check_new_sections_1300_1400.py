#!/usr/bin/env python3
"""
Тест точности новых секций 1300-1400.

Для каждой секции минимум 5 уникальных запросов, имитирующих клиента.
Проверяем, что retriever находит нужную секцию в топ-1.

Запуск: python3 check_new_sections_1300_1400.py
"""

import sys
import os
import time
from typing import List, Tuple, Dict
from dataclasses import dataclass

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
from src.knowledge.retriever import CascadeRetriever, reset_retriever

# =============================================================================
# Тестовые запросы для новых секций 1300-1400
# Формат: (запрос, ожидаемый topic, описание)
# =============================================================================

TEST_QUERIES: List[Tuple[str, str, str]] = [
    # =========================================================================
    # EQUIPMENT - МОНОБЛОКИ И КОМПЛЕКТЫ (1300-1324)
    # =========================================================================

    # equipment_kit_pro_1300
    ("где посмотреть комплект про?", "equipment_kit_pro_1300", "комплект про"),
    ("ссылка на комплект PRO пожалуйста", "equipment_kit_pro_1300", "ссылка PRO"),
    ("каталог с комплектом про есть?", "equipment_kit_pro_1300", "каталог про"),
    ("полный набор оборудования PRO где?", "equipment_kit_pro_1300", "полный набор"),
    ("комплект для быстрого обслуживания покажите", "equipment_kit_pro_1300", "быстрое обслуживание"),

    # equipment_wipon_5in1_1301
    ("расскажите про моноблок 5 в 1", "equipment_wipon_5in1_1301", "моноблок 5в1"),
    ("wipon 5 в 1 что это такое?", "equipment_wipon_5in1_1301", "что это 5в1"),
    ("кассовый моноблок 5в1 подробнее", "equipment_wipon_5in1_1301", "подробнее 5в1"),
    ("устройство всё в одном wipon", "equipment_wipon_5in1_1301", "всё в одном"),
    ("компактный моноблок для небольшого магазина", "equipment_wipon_5in1_1301", "компактный"),

    # equipment_wipon_5in1_photo_1302
    ("фото моноблока 5 в 1 пришлите", "equipment_wipon_5in1_photo_1302", "фото 5в1"),
    ("как выглядит wipon 5 в 1?", "equipment_wipon_5in1_photo_1302", "выглядит 5в1"),
    ("изображение кассы 5в1 есть?", "equipment_wipon_5in1_photo_1302", "изображение"),
    ("покажите фото wipon 5 в 1 в сборе", "equipment_wipon_5in1_photo_1302", "в сборе"),
    ("снимок моноблока 5в1 можно?", "equipment_wipon_5in1_photo_1302", "снимок"),

    # equipment_wipon_5in1_link_1303
    ("ссылка на страницу wipon 5 в 1", "equipment_wipon_5in1_link_1303", "ссылка страница"),
    ("каталог с моноблоком 5в1 где?", "equipment_wipon_5in1_link_1303", "каталог"),
    ("где подробнее про 5 в 1 почитать?", "equipment_wipon_5in1_link_1303", "подробнее"),
    ("страница товара wipon 5в1", "equipment_wipon_5in1_link_1303", "страница товара"),
    ("карточка моноблока 5 в 1", "equipment_wipon_5in1_link_1303", "карточка"),

    # equipment_pos_duo_link_1304
    ("расскажите про pos duo подробнее", "equipment_pos_duo_link_1304", "pos duo подробнее"),
    ("моноблок wipon duo что это?", "equipment_pos_duo_link_1304", "duo что это"),
    ("касса с двумя экранами duo", "equipment_pos_duo_link_1304", "два экрана"),
    ("pos duo для магазина подойдёт?", "equipment_pos_duo_link_1304", "duo для магазина"),
    ("wipon duo характеристики", "equipment_pos_duo_link_1304", "duo характеристики"),

    # equipment_pos_duo_video_1305
    ("видео pos duo есть?", "equipment_pos_duo_video_1305", "видео duo"),
    ("видеообзор моноблока duo покажите", "equipment_pos_duo_video_1305", "видеообзор"),
    ("короткий ролик про wipon duo", "equipment_pos_duo_video_1305", "ролик duo"),
    ("демонстрация pos duo на видео", "equipment_pos_duo_video_1305", "демонстрация"),
    ("можно посмотреть duo в действии?", "equipment_pos_duo_video_1305", "в действии"),

    # equipment_pos_duo_photo_1306
    ("фото pos duo пришлите", "equipment_pos_duo_photo_1306", "фото duo"),
    ("как выглядит wipon duo?", "equipment_pos_duo_photo_1306", "выглядит duo"),
    ("снимки моноблока duo есть?", "equipment_pos_duo_photo_1306", "снимки duo"),
    ("изображение pos duo поближе", "equipment_pos_duo_photo_1306", "поближе duo"),
    ("картинка кассы duo", "equipment_pos_duo_photo_1306", "картинка"),

    # equipment_pos_premium_view_1307
    ("как выглядит pos premium?", "equipment_pos_premium_view_1307", "выглядит premium"),
    ("внешний вид моноблока премиум", "equipment_pos_premium_view_1307", "внешний вид"),
    ("pos premium покажите на фото", "equipment_pos_premium_view_1307", "покажите premium"),
    ("премиум моноблок как смотрится?", "equipment_pos_premium_view_1307", "смотрится"),
    ("wipon premium на кассе как?", "equipment_pos_premium_view_1307", "на кассе"),

    # equipment_pos_premium_photo_1308
    ("фото pos premium в сборе", "equipment_pos_premium_photo_1308", "в сборе premium"),
    ("изображение премиум моноблока", "equipment_pos_premium_photo_1308", "изображение"),
    ("реальные снимки pos premium", "equipment_pos_premium_photo_1308", "реальные снимки"),
    ("фотографии wipon premium", "equipment_pos_premium_photo_1308", "фотографии"),
    ("premium как выглядит вживую?", "equipment_pos_premium_photo_1308", "вживую"),

    # equipment_pos_premium_send_photo_1309
    ("отправьте фото pos premium", "equipment_pos_premium_send_photo_1309", "отправьте фото"),
    ("скиньте снимки премиум моноблока", "equipment_pos_premium_send_photo_1309", "скиньте"),
    ("крупные фото premium пожалуйста", "equipment_pos_premium_send_photo_1309", "крупные"),
    ("хочу посмотреть premium поближе", "equipment_pos_premium_send_photo_1309", "поближе"),
    ("можете выслать фото премиума?", "equipment_pos_premium_send_photo_1309", "выслать"),

    # equipment_quadro_video_1310
    ("видео wipon quadro покажите", "equipment_quadro_video_1310", "видео quadro"),
    ("ролик про моноблок квадро", "equipment_quadro_video_1310", "ролик квадро"),
    ("quadro с весами видеообзор", "equipment_quadro_video_1310", "с весами видео"),
    ("как работает quadro на видео?", "equipment_quadro_video_1310", "работает видео"),
    ("демонстрация касса с весами quadro", "equipment_quadro_video_1310", "демонстрация"),

    # equipment_quadro_demo_1311
    ("quadro как взвешивает товар?", "equipment_quadro_demo_1311", "взвешивает"),
    ("покажите работу quadro с весами", "equipment_quadro_demo_1311", "работу с весами"),
    ("моноблок квадро взвешивание демо", "equipment_quadro_demo_1311", "взвешивание"),
    ("quadro пробивает весовой товар как?", "equipment_quadro_demo_1311", "весовой товар"),
    ("видео как quadro печатает чек после взвешивания", "equipment_quadro_demo_1311", "печатает чек"),

    # equipment_quadro_appearance_1312
    ("как выглядит wipon quadro?", "equipment_quadro_appearance_1312", "выглядит quadro"),
    ("внешний вид квадро", "equipment_quadro_appearance_1312", "внешний вид"),
    ("фото quadro пришлите", "equipment_quadro_appearance_1312", "фото quadro"),
    ("quadro компактный какой?", "equipment_quadro_appearance_1312", "компактный"),
    ("моноблок quadro снимки", "equipment_quadro_appearance_1312", "снимки"),

    # equipment_triple_live_1313
    ("wipon triple вживую покажите", "equipment_triple_live_1313", "triple вживую"),
    ("онлайн показ моноблока triple", "equipment_triple_live_1313", "онлайн показ"),
    ("triple демонстрация можно?", "equipment_triple_live_1313", "демонстрация triple"),
    ("хочу увидеть triple в работе", "equipment_triple_live_1313", "в работе"),
    ("касса triple с весами покажите", "equipment_triple_live_1313", "triple с весами"),

    # equipment_triple_link_1314
    ("ссылка на wipon triple", "equipment_triple_link_1314", "ссылка triple"),
    ("подробнее про triple где?", "equipment_triple_link_1314", "подробнее"),
    ("обзор моноблока triple", "equipment_triple_link_1314", "обзор triple"),
    ("triple для продуктового магазина", "equipment_triple_link_1314", "продуктовый"),
    ("triple характеристики и описание", "equipment_triple_link_1314", "характеристики"),

    # equipment_triple_view_1315
    ("как выглядит wipon triple?", "equipment_triple_view_1315", "выглядит triple"),
    ("внешний вид triple пришлите", "equipment_triple_view_1315", "внешний вид"),
    ("фото triple живые", "equipment_triple_view_1315", "живые фото"),
    ("triple снимки моноблока", "equipment_triple_view_1315", "снимки"),
    ("видео triple как смотрится", "equipment_triple_view_1315", "видео"),

    # equipment_pos_i3_video_1316
    ("видео pos i3 есть?", "equipment_pos_i3_video_1316", "видео i3"),
    ("ролик про моноблок i3", "equipment_pos_i3_video_1316", "ролик i3"),
    ("как работает pos i3?", "equipment_pos_i3_video_1316", "работает i3"),
    ("демо pos i 3 на видео", "equipment_pos_i3_video_1316", "демо"),
    ("i3 или i5 какой выбрать видео", "equipment_pos_i3_video_1316", "i3 или i5"),

    # equipment_pos_i3_overview_1317
    ("видеообзор pos i3", "equipment_pos_i3_overview_1317", "видеообзор i3"),
    ("обзор моноблока i3 покажите", "equipment_pos_i3_overview_1317", "обзор"),
    ("pos i3 демонстрация работы", "equipment_pos_i3_overview_1317", "демонстрация"),
    ("i3 стабильность и простота", "equipment_pos_i3_overview_1317", "стабильность"),
    ("pos i3 запуск и настройка", "equipment_pos_i3_overview_1317", "запуск"),

    # equipment_pos_i3_photo_1318
    ("фото pos i3 крупным планом", "equipment_pos_i3_photo_1318", "фото крупно"),
    ("как выглядит моноблок i3?", "equipment_pos_i3_photo_1318", "выглядит"),
    ("снимки pos i 3 пришлите", "equipment_pos_i3_photo_1318", "снимки"),
    ("i3 фото в черном цвете", "equipment_pos_i3_photo_1318", "черный"),
    ("pos i3 белый корпус фото", "equipment_pos_i3_photo_1318", "белый"),

    # equipment_pos_i5_link_1319
    ("pos i5 подробнее где посмотреть?", "equipment_pos_i5_link_1319", "подробнее i5"),
    ("ссылка на моноблок i5", "equipment_pos_i5_link_1319", "ссылка i5"),
    ("i5 мощнее чем i3?", "equipment_pos_i5_link_1319", "мощнее"),
    ("обзор pos i5 пришлите", "equipment_pos_i5_link_1319", "обзор i5"),
    ("pos i 5 для большого потока", "equipment_pos_i5_link_1319", "большой поток"),

    # equipment_pos_i3_i5_view_1320
    ("фото i3 и i5 вместе", "equipment_pos_i3_i5_view_1320", "фото вместе"),
    ("сравнение внешнего вида i3 i5", "equipment_pos_i3_i5_view_1320", "сравнение"),
    ("как выглядят моноблоки i3 и i5?", "equipment_pos_i3_i5_view_1320", "выглядят"),
    ("набор фото pos i3 i5", "equipment_pos_i3_i5_view_1320", "набор фото"),
    ("оба моноблока i3 i5 покажите", "equipment_pos_i3_i5_view_1320", "оба"),

    # equipment_pos_i3_i5_demo_1321
    ("демо i3 и i5 онлайн можно?", "equipment_pos_i3_i5_demo_1321", "демо онлайн"),
    ("покажите моноблоки i3 i5 вживую", "equipment_pos_i3_i5_demo_1321", "вживую"),
    ("онлайн демонстрация pos i3 i5", "equipment_pos_i3_i5_demo_1321", "онлайн демонстрация"),
    ("хочу увидеть работу i3 и i5", "equipment_pos_i3_i5_demo_1321", "увидеть работу"),
    ("показ интерфейса моноблоков", "equipment_pos_i3_i5_demo_1321", "интерфейс"),

    # equipment_wipon_screen_live_1322
    ("wipon screen вживую покажите", "equipment_wipon_screen_live_1322", "screen вживую"),
    ("экран покупателя wipon демо", "equipment_wipon_screen_live_1322", "экран покупателя"),
    ("кассовый экран screen как работает?", "equipment_wipon_screen_live_1322", "как работает"),
    ("screen для покупателя видео", "equipment_wipon_screen_live_1322", "для покупателя"),
    ("дисплей wipon screen показать", "equipment_wipon_screen_live_1322", "дисплей"),

    # equipment_wipon_screen_video_1323
    ("видео wipon screen", "equipment_wipon_screen_video_1323", "видео screen"),
    ("как экран показывает сумму?", "equipment_wipon_screen_video_1323", "показывает сумму"),
    ("screen видеообзор работы", "equipment_wipon_screen_video_1323", "видеообзор"),
    ("экран покупателя на видео", "equipment_wipon_screen_video_1323", "на видео"),
    ("screen помогает избежать ошибок?", "equipment_wipon_screen_video_1323", "ошибки"),

    # equipment_wipon_screen_photo_1324
    ("фото wipon screen", "equipment_wipon_screen_photo_1324", "фото screen"),
    ("как выглядит экран покупателя?", "equipment_wipon_screen_photo_1324", "выглядит"),
    ("снимки screen детальные", "equipment_wipon_screen_photo_1324", "детальные"),
    ("wipon screen матрица какая?", "equipment_wipon_screen_photo_1324", "матрица"),
    ("регулировка экрана screen", "equipment_wipon_screen_photo_1324", "регулировка"),

    # =========================================================================
    # EQUIPMENT - ПРИНТЕРЫ (1325-1335)
    # =========================================================================

    # equipment_xprinter_58_photo_1325
    ("фото принтера xprinter 58", "equipment_xprinter_58_photo_1325", "фото 58"),
    ("x-printer 58 как выглядит?", "equipment_xprinter_58_photo_1325", "выглядит"),
    ("снимки принтера чеков 58мм", "equipment_xprinter_58_photo_1325", "58мм"),
    ("xprinter 58 iint фото", "equipment_xprinter_58_photo_1325", "iint"),
    ("маленький принтер чеков фото", "equipment_xprinter_58_photo_1325", "маленький"),

    # equipment_xprinter_58_view_1326
    ("внешний вид xprinter 58", "equipment_xprinter_58_view_1326", "внешний вид"),
    ("как смотрится принтер 58мм?", "equipment_xprinter_58_view_1326", "смотрится"),
    ("xprinter краткий обзор", "equipment_xprinter_58_view_1326", "обзор"),
    ("карточка товара x-printer", "equipment_xprinter_58_view_1326", "карточка"),
    ("принтер 58 компактный какой?", "equipment_xprinter_58_view_1326", "компактный"),

    # equipment_xprinter_58_send_1327
    ("пришлите фото xprinter с разных ракурсов", "equipment_xprinter_58_send_1327", "ракурсы"),
    ("отправьте снимки принтера 58", "equipment_xprinter_58_send_1327", "отправьте"),
    ("xprinter 58 iint установка фото", "equipment_xprinter_58_send_1327", "установка"),
    ("как выглядит x-printer в работе?", "equipment_xprinter_58_send_1327", "в работе"),
    ("термопечать xprinter фото", "equipment_xprinter_58_send_1327", "термопечать"),

    # equipment_xprinter_e200l_video_1330
    ("видео xprinter e200l", "equipment_xprinter_e200l_video_1330", "видео e200l"),
    ("принтер 80мм видеообзор", "equipment_xprinter_e200l_video_1330", "80мм видео"),
    ("e 200 l как печатает?", "equipment_xprinter_e200l_video_1330", "как печатает"),
    ("быстрый принтер 230мм в секунду демо", "equipment_xprinter_e200l_video_1330", "230мм"),
    ("автоотрез принтер видео", "equipment_xprinter_e200l_video_1330", "автоотрез"),

    # equipment_xprinter_e200l_photo_1331
    ("фото xprinter e200l", "equipment_xprinter_e200l_photo_1331", "фото"),
    ("снимки принтера e 200 l", "equipment_xprinter_e200l_photo_1331", "снимки"),
    ("как выглядит e200l?", "equipment_xprinter_e200l_photo_1331", "выглядит"),
    ("принтер 80мм фото крупно", "equipment_xprinter_e200l_photo_1331", "крупно"),
    ("e200l usb lan фото", "equipment_xprinter_e200l_photo_1331", "usb lan"),

    # equipment_xprinter_compare_1332
    ("сравнение xprinter 58 и e200l", "equipment_xprinter_compare_1332", "сравнение"),
    ("какой принтер выбрать 58 или 80?", "equipment_xprinter_compare_1332", "58 или 80"),
    ("58 iint vs e200l что лучше?", "equipment_xprinter_compare_1332", "что лучше"),
    ("разница между принтерами xprinter", "equipment_xprinter_compare_1332", "разница"),
    ("принтеры чеков сравнить модели", "equipment_xprinter_compare_1332", "сравнить"),

    # equipment_xp420b_photo_1333
    ("фото принтера этикеток xp420b", "equipment_xp420b_photo_1333", "фото этикеток"),
    ("xp 420 b как выглядит?", "equipment_xp420b_photo_1333", "выглядит"),
    ("принтер штрихкодов фото", "equipment_xp420b_photo_1333", "штрихкодов"),
    ("снимки xp420b пришлите", "equipment_xp420b_photo_1333", "снимки"),
    ("печать этикеток принтер фото", "equipment_xp420b_photo_1333", "печать этикеток"),

    # equipment_xp420b_assembled_1334
    ("xp420b на рабочем месте фото", "equipment_xp420b_assembled_1334", "рабочее место"),
    ("принтер этикеток в сборе", "equipment_xp420b_assembled_1334", "в сборе"),
    ("как загружается рулон в xp420b?", "equipment_xp420b_assembled_1334", "рулон"),
    ("xp 420 b установленный фото", "equipment_xp420b_assembled_1334", "установленный"),
    ("печать ценников принтер фото", "equipment_xp420b_assembled_1334", "ценников"),

    # equipment_xp420b_closeup_1335
    ("крупные фото xp420b", "equipment_xp420b_closeup_1335", "крупные"),
    ("примеры этикеток с xp420b", "equipment_xp420b_closeup_1335", "примеры"),
    ("детальные снимки принтера этикеток", "equipment_xp420b_closeup_1335", "детальные"),
    ("xp420b корпус крупным планом", "equipment_xp420b_closeup_1335", "крупным планом"),
    ("какие этикетки печатает xp420b?", "equipment_xp420b_closeup_1335", "какие этикетки"),

    # =========================================================================
    # EQUIPMENT - СКАНЕРЫ (1336-1373)
    # =========================================================================

    # equipment_scanner_wireless_wpb930_1336
    ("беспроводной сканер wipon wpb930", "equipment_scanner_wireless_wpb930_1336", "wpb930"),
    ("сканер по радиоканалу wipon", "equipment_scanner_wireless_wpb930_1336", "радиоканал"),
    ("wpb 930 фото пришлите", "equipment_scanner_wireless_wpb930_1336", "фото"),
    ("сканер 2d беспроводной wipon", "equipment_scanner_wireless_wpb930_1336", "2d"),
    ("сканер выдерживает падения?", "equipment_scanner_wireless_wpb930_1336", "падения"),

    # equipment_scanner_wpb930_live_1337
    ("wpb930 вживую покажите", "equipment_scanner_wpb930_live_1337", "вживую"),
    ("видео беспроводного сканера wipon", "equipment_scanner_wpb930_live_1337", "видео"),
    ("сканер wpb 930 мобильный демо", "equipment_scanner_wpb930_live_1337", "мобильный"),
    ("дальность работы сканера wpb930", "equipment_scanner_wpb930_live_1337", "дальность"),
    ("легкий сканер для зала видео", "equipment_scanner_wpb930_live_1337", "для зала"),

    # equipment_scanner_wpb930_link_1340
    ("ссылка на сканер wpb930", "equipment_scanner_wpb930_link_1340", "ссылка"),
    ("спецификация wpb 930", "equipment_scanner_wpb930_link_1340", "спецификация"),
    ("сканер 1d 2d коды wpb930", "equipment_scanner_wpb930_link_1340", "1d 2d"),
    ("звуковое подтверждение сканера", "equipment_scanner_wpb930_link_1340", "звуковое"),
    ("wpb930 характеристики", "equipment_scanner_wpb930_link_1340", "характеристики"),

    # equipment_scanner_wp930z_photo_1341
    ("фото сканера wp930z", "equipment_scanner_wp930z_photo_1341", "фото"),
    ("wp 930 z как выглядит?", "equipment_scanner_wp930z_photo_1341", "выглядит"),
    ("проводной сканер wipon фото", "equipment_scanner_wp930z_photo_1341", "проводной"),
    ("usb сканер wipon снимки", "equipment_scanner_wp930z_photo_1341", "usb"),
    ("wp930z пришлите фото", "equipment_scanner_wp930z_photo_1341", "пришлите"),

    # equipment_scanner_wp930z_video_1342
    ("видео сканера wp930z", "equipment_scanner_wp930z_video_1342", "видео"),
    ("wp 930 z скорость сканирования", "equipment_scanner_wp930z_video_1342", "скорость"),
    ("как считывает мелкие коды wp930z?", "equipment_scanner_wp930z_video_1342", "мелкие коды"),
    ("видеообзор проводного сканера", "equipment_scanner_wp930z_video_1342", "видеообзор"),
    ("wp930z демонстрация работы", "equipment_scanner_wp930z_video_1342", "демонстрация"),

    # equipment_scanner_wp930z_closeup_1343
    ("крупные фото wp930z", "equipment_scanner_wp930z_closeup_1343", "крупные"),
    ("рукоятка сканера wp930z", "equipment_scanner_wp930z_closeup_1343", "рукоятка"),
    ("корпус wp 930 z детально", "equipment_scanner_wp930z_closeup_1343", "корпус"),
    ("сканер wp930z крупным планом", "equipment_scanner_wp930z_closeup_1343", "планом"),
    ("удобный сканер wipon фото", "equipment_scanner_wp930z_closeup_1343", "удобный"),

    # equipment_scanner_wpb930_detail_1344
    ("детальное фото wpb930", "equipment_scanner_wpb930_detail_1344", "детальное"),
    ("wpb 930 компактный какой?", "equipment_scanner_wpb930_detail_1344", "компактный"),
    ("сканер для активной торговли", "equipment_scanner_wpb930_detail_1344", "активная торговля"),
    ("wpb930 прочность и падения", "equipment_scanner_wpb930_detail_1344", "прочность"),
    ("беспроводной сканер детализация", "equipment_scanner_wpb930_detail_1344", "детализация"),

    # equipment_scanner_wpb930_overview_1345
    ("обзор сканера wpb930", "equipment_scanner_wpb930_overview_1345", "обзор"),
    ("wpb 930 как работает на расстоянии?", "equipment_scanner_wpb930_overview_1345", "расстояние"),
    ("сканер с сигналом подтверждения", "equipment_scanner_wpb930_overview_1345", "сигнал"),
    ("скорость считывания wpb930", "equipment_scanner_wpb930_overview_1345", "скорость"),
    ("краткий обзор беспроводного сканера", "equipment_scanner_wpb930_overview_1345", "краткий"),

    # equipment_scanner_wpb930_workplace_1348
    ("wpb930 на кассе фото", "equipment_scanner_wpb930_workplace_1348", "на кассе"),
    ("сканер в рабочей зоне", "equipment_scanner_wpb930_workplace_1348", "рабочая зона"),
    ("wpb 930 для магазина с залом", "equipment_scanner_wpb930_workplace_1348", "с залом"),
    ("мобильный сканер на кассовом месте", "equipment_scanner_wpb930_workplace_1348", "кассовое место"),
    ("прочный сканер в работе фото", "equipment_scanner_wpb930_workplace_1348", "в работе"),

    # equipment_scanner_zebra_ds2208_1349
    ("сканер zebra ds2208 фото", "equipment_scanner_zebra_ds2208_1349", "фото"),
    ("zebra ds 2208 характеристики", "equipment_scanner_zebra_ds2208_1349", "характеристики"),
    ("сканер с гарантией 4 года", "equipment_scanner_zebra_ds2208_1349", "гарантия"),
    ("zebra ip42 защита", "equipment_scanner_zebra_ds2208_1349", "ip42"),
    ("профессиональный сканер zebra", "equipment_scanner_zebra_ds2208_1349", "профессиональный"),

    # equipment_scanner_zebra_live_1350
    ("zebra ds2208 вживую покажите", "equipment_scanner_zebra_live_1350", "вживую"),
    ("видео сканера zebra", "equipment_scanner_zebra_live_1350", "видео"),
    ("как zebra лежит в руке?", "equipment_scanner_zebra_live_1350", "в руке"),
    ("демонстрация zebra ds2208", "equipment_scanner_zebra_live_1350", "демонстрация"),
    ("zebra быстро читает коды видео", "equipment_scanner_zebra_live_1350", "быстро"),

    # equipment_scanner_zebra_video_1351
    ("видеообзор zebra ds2208", "equipment_scanner_zebra_video_1351", "видеообзор"),
    ("zebra качество считывания видео", "equipment_scanner_zebra_video_1351", "качество"),
    ("сканер zebra мелкие коды демо", "equipment_scanner_zebra_video_1351", "мелкие коды"),
    ("ds 2208 в работе видео", "equipment_scanner_zebra_video_1351", "в работе"),
    ("zebra защита ip42 демо", "equipment_scanner_zebra_video_1351", "защита"),

    # equipment_scanner_stationary_wipon_1352
    ("стационарный сканер wipon фото", "equipment_scanner_stationary_wipon_1352", "стационарный фото"),
    ("сканер без кнопки wipon", "equipment_scanner_stationary_wipon_1352", "без кнопки"),
    ("сканер при наведении wipon", "equipment_scanner_stationary_wipon_1352", "наведение"),
    ("1650 сканов в секунду сканер", "equipment_scanner_stationary_wipon_1352", "1650"),
    ("быстрый стационарный сканер", "equipment_scanner_stationary_wipon_1352", "быстрый"),

    # equipment_scanner_stationary_assembled_1353
    ("стационарный сканер на столе фото", "equipment_scanner_stationary_assembled_1353", "на столе"),
    ("сканер освобождает руки", "equipment_scanner_stationary_assembled_1353", "освобождает руки"),
    ("автоматическое сканирование товара", "equipment_scanner_stationary_assembled_1353", "автоматическое"),
    ("сканер при поднесении товара", "equipment_scanner_stationary_assembled_1353", "поднесении"),
    ("стационарный сканер на кассе", "equipment_scanner_stationary_assembled_1353", "на кассе"),

    # equipment_scanner_stationary_video_1354
    ("видео стационарного сканера wipon", "equipment_scanner_stationary_video_1354", "видео"),
    ("скорость стационарного сканера", "equipment_scanner_stationary_video_1354", "скорость"),
    ("сканер для потока покупателей видео", "equipment_scanner_stationary_video_1354", "поток"),
    ("стационарный сканер демо", "equipment_scanner_stationary_video_1354", "демо"),
    ("удобство стационарного сканера", "equipment_scanner_stationary_video_1354", "удобство"),

    # equipment_scanner_wp7600l_link_1357
    ("сканер wp7600l характеристики", "equipment_scanner_wp7600l_link_1357", "характеристики"),
    ("wp 7600 l спецификация", "equipment_scanner_wp7600l_link_1357", "спецификация"),
    ("стационарный сканер для гипермаркета", "equipment_scanner_wp7600l_link_1357", "гипермаркет"),
    ("сканер 1650 сканов wp7600l", "equipment_scanner_wp7600l_link_1357", "1650"),
    ("wp7600l для больших очередей", "equipment_scanner_wp7600l_link_1357", "очереди"),

    # equipment_scanner_wp7600l_photo_1360
    ("фото сканера wp7600l", "equipment_scanner_wp7600l_photo_1360", "фото"),
    ("wp 7600 l в кассовой зоне", "equipment_scanner_wp7600l_photo_1360", "кассовая зона"),
    ("снимки стационарного сканера wp7600l", "equipment_scanner_wp7600l_photo_1360", "снимки"),
    ("wp7600l ускоряет продажи фото", "equipment_scanner_wp7600l_photo_1360", "ускоряет"),
    ("сканер wp7600l на кассе", "equipment_scanner_wp7600l_photo_1360", "на кассе"),

    # equipment_scanner_wp7600l_video_1361
    ("видео сканера wp7600l", "equipment_scanner_wp7600l_video_1361", "видео"),
    ("wp 7600 l без кнопок демо", "equipment_scanner_wp7600l_video_1361", "без кнопок"),
    ("как работает wp7600l видео", "equipment_scanner_wp7600l_video_1361", "работает"),
    ("высокая скорость wp7600l видео", "equipment_scanner_wp7600l_video_1361", "высокая скорость"),
    ("товар подносят к wp7600l", "equipment_scanner_wp7600l_video_1361", "подносят"),

    # equipment_scanner_stand_1364
    ("подставка для сканера фото", "equipment_scanner_stand_1364", "подставка фото"),
    ("стандартная подставка сканера", "equipment_scanner_stand_1364", "стандартная"),
    ("подставка освобождает руки", "equipment_scanner_stand_1364", "руки"),
    ("подставка для ручного сканера", "equipment_scanner_stand_1364", "ручной"),
    ("подставка пластиковая сканер", "equipment_scanner_stand_1364", "пластиковая"),

    # equipment_scanner_stand_link_1365
    ("ссылка на подставку сканера", "equipment_scanner_stand_link_1365", "ссылка"),
    ("карточка подставки товар", "equipment_scanner_stand_link_1365", "карточка"),
    ("подставка совместимость сканеров", "equipment_scanner_stand_link_1365", "совместимость"),
    ("компактная подставка сканер", "equipment_scanner_stand_link_1365", "компактная"),
    ("надежная подставка wipon", "equipment_scanner_stand_link_1365", "надежная"),

    # equipment_scanner_stand_video_1368
    ("видео подставки для сканера", "equipment_scanner_stand_video_1368", "видео"),
    ("как работает подставка на кассе?", "equipment_scanner_stand_video_1368", "работает"),
    ("подставка свободные руки видео", "equipment_scanner_stand_video_1368", "свободные"),
    ("товар подносят к подставке демо", "equipment_scanner_stand_video_1368", "подносят"),
    ("ускорение работы с подставкой", "equipment_scanner_stand_video_1368", "ускорение"),

    # equipment_scanner_stand_zebra_1369
    ("подставка zebra оригинальная", "equipment_scanner_stand_zebra_1369", "zebra"),
    ("подставка для серии ds zebra", "equipment_scanner_stand_zebra_1369", "ds"),
    ("оригинальная подставка для zebra", "equipment_scanner_stand_zebra_1369", "оригинальная"),
    ("подставка интенсивное использование", "equipment_scanner_stand_zebra_1369", "интенсивное"),
    ("устойчивая подставка zebra", "equipment_scanner_stand_zebra_1369", "устойчивая"),

    # equipment_scanner_stand_zebra_video_1372
    ("видео подставки zebra", "equipment_scanner_stand_zebra_video_1372", "видео zebra"),
    ("подставка zebra на кассе демо", "equipment_scanner_stand_zebra_video_1372", "демо"),
    ("как подставка zebra ускоряет работу?", "equipment_scanner_stand_zebra_video_1372", "ускоряет"),
    ("подставка zebra освобождает руки", "equipment_scanner_stand_zebra_video_1372", "освобождает"),
    ("процесс на кассе с подставкой zebra", "equipment_scanner_stand_zebra_video_1372", "процесс"),

    # equipment_scanner_stand_demo_1373
    ("показ подставки для сканера", "equipment_scanner_stand_demo_1373", "показ"),
    ("демонстрация подставки вживую", "equipment_scanner_stand_demo_1373", "демонстрация"),
    ("сканер в подставке покажите", "equipment_scanner_stand_demo_1373", "покажите"),
    ("процесс считывания с подставкой", "equipment_scanner_stand_demo_1373", "считывания"),
    ("подставка короткий показ", "equipment_scanner_stand_demo_1373", "короткий"),

    # =========================================================================
    # EQUIPMENT - ДЕНЕЖНЫЕ ЯЩИКИ И ВЕСЫ (1374-1388)
    # =========================================================================

    # equipment_cash_drawer_wipon_1374
    ("денежный ящик wipon фото", "equipment_cash_drawer_wipon_1374", "фото"),
    ("кассовый ящик 5 отделений", "equipment_cash_drawer_wipon_1374", "5 отделений"),
    ("ящик для денег wipon", "equipment_cash_drawer_wipon_1374", "для денег"),
    ("денежный ящик автооткрытие", "equipment_cash_drawer_wipon_1374", "автооткрытие"),
    ("ящик с замком для кассы", "equipment_cash_drawer_wipon_1374", "замок"),

    # equipment_cash_drawer_video_1375
    ("видео денежного ящика wipon", "equipment_cash_drawer_video_1375", "видео"),
    ("как открывается ящик автоматически?", "equipment_cash_drawer_video_1375", "открывается"),
    ("организация отделений ящика видео", "equipment_cash_drawer_video_1375", "отделений"),
    ("денежный ящик демо", "equipment_cash_drawer_video_1375", "демо"),
    ("ящик для купюр и монет видео", "equipment_cash_drawer_video_1375", "купюр"),

    # equipment_cash_drawer_overview_1376
    ("видеообзор денежного ящика", "equipment_cash_drawer_overview_1376", "видеообзор"),
    ("как подключается ящик к кассе?", "equipment_cash_drawer_overview_1376", "подключается"),
    ("денежный ящик в работе смена", "equipment_cash_drawer_overview_1376", "смена"),
    ("обзор кассового ящика wipon", "equipment_cash_drawer_overview_1376", "обзор"),
    ("ящик для кассы подключение", "equipment_cash_drawer_overview_1376", "подключение"),

    # equipment_scales_rongta_1377
    ("весы rongta с печатью этикеток", "equipment_scales_rongta_1377", "печать этикеток"),
    ("весы для продуктовых секций", "equipment_scales_rongta_1377", "продуктовых"),
    ("rongta весы фото", "equipment_scales_rongta_1377", "фото"),
    ("весы большой ассортимент товаров", "equipment_scales_rongta_1377", "ассортимент"),
    ("весы rongta примеры этикеток", "equipment_scales_rongta_1377", "примеры"),

    # equipment_scales_rongta_video_1378
    ("видео весов rongta", "equipment_scales_rongta_video_1378", "видео"),
    ("rongta печать ценников видео", "equipment_scales_rongta_video_1378", "ценников"),
    ("как работают весы rongta?", "equipment_scales_rongta_video_1378", "работают"),
    ("видеообзор весов rongta", "equipment_scales_rongta_video_1378", "видеообзор"),
    ("весы rongta демонстрация", "equipment_scales_rongta_video_1378", "демонстрация"),

    # equipment_scales_rongta_photo_1379
    ("фото весов rongta на прилавке", "equipment_scales_rongta_photo_1379", "прилавке"),
    ("весы rongta крупные планы", "equipment_scales_rongta_photo_1379", "крупные"),
    ("печатающий узел rongta фото", "equipment_scales_rongta_photo_1379", "печатающий"),
    ("rongta снимки весов", "equipment_scales_rongta_photo_1379", "снимки"),
    ("весы с принтером фото", "equipment_scales_rongta_photo_1379", "с принтером"),

    # equipment_scales_smart_wipon_1380
    ("умные весы wipon фото", "equipment_scales_smart_wipon_1380", "умные весы"),
    ("весы передают вес в систему", "equipment_scales_smart_wipon_1380", "в систему"),
    ("smart весы wipon", "equipment_scales_smart_wipon_1380", "smart"),
    ("весы до 30 кг wipon", "equipment_scales_smart_wipon_1380", "30 кг"),
    ("автоматические весы wipon", "equipment_scales_smart_wipon_1380", "автоматические"),

    # equipment_scales_smart_assembled_1381
    ("умные весы в кассовой зоне фото", "equipment_scales_smart_assembled_1381", "кассовая зона"),
    ("вес в чек автоматически весы", "equipment_scales_smart_assembled_1381", "в чек"),
    ("весы wipon снижают ошибки", "equipment_scales_smart_assembled_1381", "ошибки"),
    ("весы wipon ускоряют обслуживание", "equipment_scales_smart_assembled_1381", "ускоряют"),
    ("смарт весы на кассе фото", "equipment_scales_smart_assembled_1381", "на кассе"),

    # equipment_scales_smart_closeup_1382
    ("крупные фото весов wipon", "equipment_scales_smart_closeup_1382", "крупные"),
    ("платформа весов wipon фото", "equipment_scales_smart_closeup_1382", "платформа"),
    ("дисплей весов wipon", "equipment_scales_smart_closeup_1382", "дисплей"),
    ("весы точность 100г фото", "equipment_scales_smart_closeup_1382", "точность"),
    ("кабели весов wipon фото", "equipment_scales_smart_closeup_1382", "кабели"),

    # equipment_pocket_scanner_1383
    ("карманный сканер wipon", "equipment_pocket_scanner_1383", "карманный"),
    ("pocket scanner фото", "equipment_pocket_scanner_1383", "фото"),
    ("сканер bluetooth 2.4g", "equipment_pocket_scanner_1383", "bluetooth"),
    ("сканер дальность 30 метров", "equipment_pocket_scanner_1383", "30 метров"),
    ("сканер для выездной торговли", "equipment_pocket_scanner_1383", "выездная"),

    # equipment_pocket_scanner_live_1384
    ("pocket scanner вживую", "equipment_pocket_scanner_live_1384", "вживую"),
    ("видео карманного сканера", "equipment_pocket_scanner_live_1384", "видео"),
    ("pocket scanner мобильность демо", "equipment_pocket_scanner_live_1384", "мобильность"),
    ("скорость считывания pocket scanner", "equipment_pocket_scanner_live_1384", "скорость"),
    ("карманный сканер в работе", "equipment_pocket_scanner_live_1384", "в работе"),

    # equipment_pocket_scanner_video_1385
    ("видео pocket scanner подключение", "equipment_pocket_scanner_video_1385", "подключение"),
    ("pocket scanner usb bluetooth демо", "equipment_pocket_scanner_video_1385", "usb"),
    ("как работает pocket scanner?", "equipment_pocket_scanner_video_1385", "работает"),
    ("pocket scanner на расстоянии", "equipment_pocket_scanner_video_1385", "расстояние"),
    ("видеообзор карманного сканера", "equipment_pocket_scanner_video_1385", "видеообзор"),

    # equipment_smart_scanner_1386
    ("smart scanner wipon фото", "equipment_smart_scanner_1386", "smart scanner"),
    ("сканер аккумулятор 3000mah", "equipment_smart_scanner_1386", "аккумулятор"),
    ("wipon smart scanner характеристики", "equipment_smart_scanner_1386", "характеристики"),
    ("сканер долгая работа батарея", "equipment_smart_scanner_1386", "батарея"),
    ("умный сканер wipon", "equipment_smart_scanner_1386", "умный"),

    # equipment_smart_scanner_link_1387
    ("ссылка smart scanner wipon", "equipment_smart_scanner_link_1387", "ссылка"),
    ("спецификация smart scanner", "equipment_smart_scanner_link_1387", "спецификация"),
    ("smart scanner дальность 30м", "equipment_smart_scanner_link_1387", "дальность"),
    ("smart scanner для зала склада", "equipment_smart_scanner_link_1387", "для зала"),
    ("карточка smart scanner", "equipment_smart_scanner_link_1387", "карточка"),

    # equipment_smart_scanner_video_1388
    ("видео smart scanner wipon", "equipment_smart_scanner_video_1388", "видео"),
    ("smart scanner скорость демо", "equipment_smart_scanner_video_1388", "скорость"),
    ("автономность smart scanner видео", "equipment_smart_scanner_video_1388", "автономность"),
    ("smart scanner дальность видео", "equipment_smart_scanner_video_1388", "дальность"),
    ("как работает smart scanner?", "equipment_smart_scanner_video_1388", "работает"),

    # equipment_pos_duo_specs_1398
    ("pos duo технические характеристики", "equipment_pos_duo_specs_1398", "технические"),
    ("pos duo процессор i5", "equipment_pos_duo_specs_1398", "процессор"),
    ("pos duo 8гб озу", "equipment_pos_duo_specs_1398", "озу"),
    ("pos duo ssd 128", "equipment_pos_duo_specs_1398", "ssd"),
    ("pos duo два экрана размеры", "equipment_pos_duo_specs_1398", "размеры экранов"),

    # equipment_flower_shop_1402
    ("оборудование для цветочного магазина", "equipment_flower_shop_1402", "цветочный"),
    ("комплект для цветов алматы", "equipment_flower_shop_1402", "алматы"),
    ("pos duo для цветочного бизнеса", "equipment_flower_shop_1402", "бизнес"),
    ("оборудование цветы доставка", "equipment_flower_shop_1402", "доставка"),
    ("кассовое оборудование цветы", "equipment_flower_shop_1402", "кассовое"),

    # =========================================================================
    # SUPPORT (1389-1390)
    # =========================================================================

    # support_consulting_1389
    ("консалтинг wipon расскажите", "support_consulting_1389", "консалтинг"),
    ("бухучёт и налоги wipon consulting", "support_consulting_1389", "бухучёт"),
    ("сдача форм 910 200 300", "support_consulting_1389", "формы"),
    ("регистрация ип тоо wipon", "support_consulting_1389", "регистрация"),
    ("сопровождение проверок wipon", "support_consulting_1389", "проверки"),

    # support_report_submit_1390
    ("хочу сдать отчёт", "support_report_submit_1390", "сдать отчёт"),
    ("отчёт под ключ сделайте", "support_report_submit_1390", "под ключ"),
    ("помогите сдать форму", "support_report_submit_1390", "форму"),
    ("подготовка отчёта к сдаче", "support_report_submit_1390", "подготовка"),
    ("проверка данных для отчёта", "support_report_submit_1390", "проверка данных"),

    # =========================================================================
    # PRICING (1391-1408)
    # =========================================================================

    # pricing_mini_tariff_1391
    ("что включает тариф wipon mini?", "pricing_mini_tariff_1391", "включает mini"),
    ("тариф mini для одной точки", "pricing_mini_tariff_1391", "одна точка"),
    ("wipon mini базовый учёт", "pricing_mini_tariff_1391", "базовый"),
    ("онлайн касса mini фискализация", "pricing_mini_tariff_1391", "фискализация"),
    ("mini 5000 тенге что входит?", "pricing_mini_tariff_1391", "что входит"),

    # tis_benefits_1392
    ("какие выгоды даёт тис?", "tis_benefits_1392", "выгоды"),
    ("преимущества тис для ип", "tis_benefits_1392", "преимущества"),
    ("тис сохраняет режим ип?", "tis_benefits_1392", "режим ип"),
    ("тис повышает лимиты оборота", "tis_benefits_1392", "лимиты"),
    ("тис в реестре кгд", "tis_benefits_1392", "реестр кгд"),

    # pricing_tis_cost_1393
    ("сколько стоит тис wipon?", "pricing_tis_cost_1393", "стоит тис"),
    ("тис цена на год", "pricing_tis_cost_1393", "на год"),
    ("тис 220000 за год?", "pricing_tis_cost_1393", "220000"),
    ("тис на 2 года стоимость", "pricing_tis_cost_1393", "2 года"),
    ("тис 5 лет цена", "pricing_tis_cost_1393", "5 лет"),

    # pricing_tis_money_1394
    ("по деньгам тис сколько?", "pricing_tis_money_1394", "по деньгам"),
    ("тис минимальная стоимость", "pricing_tis_money_1394", "минимальная"),
    ("тис рассрочка есть?", "pricing_tis_money_1394", "рассрочка"),
    ("тис пакеты со скидкой", "pricing_tis_money_1394", "скидка"),
    ("тис от 22084 в месяц", "pricing_tis_money_1394", "в месяц"),

    # pricing_tis_price_1395
    ("цена на тис wipon", "pricing_tis_price_1395", "цена тис"),
    ("тис тариф стоимость", "pricing_tis_price_1395", "тариф"),
    ("рассрочка без переплаты тис", "pricing_tis_price_1395", "без переплаты"),
    ("тис 350000 на 2 года", "pricing_tis_price_1395", "350000"),
    ("тис 500000 на 5 лет", "pricing_tis_price_1395", "500000"),

    # faq_greeting_kazakh_1396
    ("сәлеметсізбе", "faq_greeting_kazakh_1396", "приветствие"),
    ("сәлем қалайсыз", "faq_greeting_kazakh_1396", "сәлем"),
    ("қайырлы күн", "faq_greeting_kazakh_1396", "қайырлы"),
    ("ассалаумағалейкүм", "faq_greeting_kazakh_1396", "ассалаум"),
    ("сәлеметсіз бе көмектесіңіз", "faq_greeting_kazakh_1396", "көмек"),

    # pricing_mini_small_shop_1397
    ("wipon mini для маленького магазина сколько?", "pricing_mini_small_shop_1397", "маленький"),
    ("программа учёта mini цена", "pricing_mini_small_shop_1397", "программа цена"),
    ("касса чеки продажи 5000", "pricing_mini_small_shop_1397", "5000"),
    ("офд без доплат mini", "pricing_mini_small_shop_1397", "офд"),
    ("небольшая торговая точка тариф", "pricing_mini_small_shop_1397", "торговая точка"),

    # pricing_flower_tariffs_1401
    ("тарифы для цветочного бизнеса", "pricing_flower_tariffs_1401", "цветочный тариф"),
    ("цветы алматы какой тариф выбрать?", "pricing_flower_tariffs_1401", "алматы выбрать"),
    ("комплект standard для цветов", "pricing_flower_tariffs_1401", "standard"),
    ("pro для цветочного магазина", "pricing_flower_tariffs_1401", "pro"),
    ("старт расширение тарифы цветы", "pricing_flower_tariffs_1401", "старт расширение"),

    # pricing_flower_advice_1403
    ("посоветуйте тариф для цветочного", "pricing_flower_advice_1403", "посоветуйте"),
    ("wipon для продажи цветов", "pricing_flower_advice_1403", "продажа"),
    ("одна точка цветы mini?", "pricing_flower_advice_1403", "одна точка"),
    ("цветы склад персонал standard", "pricing_flower_advice_1403", "склад персонал"),
    ("цветочная сеть опт pro", "pricing_flower_advice_1403", "сеть опт"),

    # pricing_clothing_tariffs_1404
    ("тарифы для магазина одежды астана", "pricing_clothing_tariffs_1404", "одежда астана"),
    ("размеры цвета склад тариф", "pricing_clothing_tariffs_1404", "размеры цвета"),
    ("одежда standard или pro?", "pricing_clothing_tariffs_1404", "standard pro"),
    ("сеть одежды расширенная аналитика", "pricing_clothing_tariffs_1404", "аналитика"),
    ("магазин одежды 220000 или 500000?", "pricing_clothing_tariffs_1404", "220000 500000"),

    # pricing_clothing_shop_1405
    ("один магазин одежды тариф", "pricing_clothing_shop_1405", "один магазин"),
    ("магазин одежды wipon standard", "pricing_clothing_shop_1405", "wipon standard"),
    ("сеть магазинов одежды pro", "pricing_clothing_shop_1405", "сеть pro"),
    ("одежда астана какой тариф?", "pricing_clothing_shop_1405", "астана тариф"),
    ("одежда опт тариф wipon", "pricing_clothing_shop_1405", "опт"),

    # pricing_autoparts_1408
    ("магазин автозапчастей mini или standard?", "pricing_autoparts_1408", "автозапчасти"),
    ("автозапчасти тариф wipon", "pricing_autoparts_1408", "тариф"),
    ("небольшая точка автозапчасти mini", "pricing_autoparts_1408", "небольшая"),
    ("склад штрихкоды автозапчасти", "pricing_autoparts_1408", "штрихкоды"),
    ("сканер принтер для автозапчастей", "pricing_autoparts_1408", "сканер принтер"),

    # =========================================================================
    # PRODUCTS (1406-1409)
    # =========================================================================

    # products_coffee_shop_1406
    ("для кофейни что посоветуете?", "products_coffee_shop_1406", "кофейня"),
    ("кофейня программа и оборудование", "products_coffee_shop_1406", "программа"),
    ("lite или standard для кофе?", "products_coffee_shop_1406", "lite standard"),
    ("wipon подходит для кофейни?", "products_coffee_shop_1406", "подходит"),
    ("калькуляция ингредиентов кофейня", "products_coffee_shop_1406", "калькуляция"),

    # products_pharmacy_1407
    ("касса для аптеки wipon", "products_pharmacy_1407", "аптека"),
    ("программа учёта для аптеки", "products_pharmacy_1407", "программа"),
    ("маркировка лекарств wipon", "products_pharmacy_1407", "маркировка"),
    ("сроки годности контроль аптека", "products_pharmacy_1407", "сроки годности"),
    ("разукомплектовка для аптеки", "products_pharmacy_1407", "разукомплектовка"),

    # products_beauty_salon_1409
    ("для салона красоты какой тариф?", "products_beauty_salon_1409", "салон красоты"),
    ("услуги mini или lite?", "products_beauty_salon_1409", "услуги"),
    ("салон красоты продажа материалов", "products_beauty_salon_1409", "материалы"),
    ("wipon для услуг тариф", "products_beauty_salon_1409", "для услуг"),
    ("только услуги mini lite", "products_beauty_salon_1409", "только услуги"),
]


@dataclass
class TestResult:
    query: str
    expected_topic: str
    description: str
    found_topic: str
    is_correct: bool
    score: float
    stage: str


def run_tests() -> List[TestResult]:
    print("\nИнициализация retriever...")
    reset_retriever()
    retriever = CascadeRetriever(use_embeddings=False)

    print(f"Загружено секций: {len(retriever.kb.sections)}")
    print(f"Всего тестов: {len(TEST_QUERIES)}")
    print("=" * 100)

    results: List[TestResult] = []
    start_total = time.perf_counter()

    for i, (query, expected_topic, description) in enumerate(TEST_QUERIES, 1):
        search_results = retriever.search(query, top_k=1)

        if search_results:
            found_topic = search_results[0].section.topic
            score = search_results[0].score
            stage = search_results[0].stage.value
        else:
            found_topic = "NOT_FOUND"
            score = 0.0
            stage = "none"

        is_correct = found_topic == expected_topic
        results.append(TestResult(query, expected_topic, description, found_topic, is_correct, score, stage))

        status = "✓" if is_correct else "✗"
        print(f"[{i:3d}/{len(TEST_QUERIES)}] [{status}] {query[:50]:<50} -> {found_topic[:40]:<40} ({score:.2f})")

    print(f"\nОбщее время: {time.perf_counter() - start_total:.1f}s")
    return results


def print_summary(results: List[TestResult]):
    print("\n" + "=" * 100)
    print("ИТОГИ")
    print("=" * 100)

    correct = sum(1 for r in results if r.is_correct)
    total = len(results)
    accuracy = correct / total * 100

    print(f"\nОбщая точность: {correct}/{total} ({accuracy:.1f}%)")

    # По категориям (по prefix topic)
    categories: Dict[str, Dict[str, int]] = {}
    for r in results:
        cat = r.expected_topic.split("_")[0]
        if cat not in categories:
            categories[cat] = {"correct": 0, "total": 0}
        categories[cat]["total"] += 1
        if r.is_correct:
            categories[cat]["correct"] += 1

    print("\nТочность по категориям:")
    print("-" * 60)
    for cat, stats in sorted(categories.items(), key=lambda x: -x[1]["total"]):
        cat_accuracy = stats["correct"] / stats["total"] * 100
        bar = "█" * int(cat_accuracy / 10) + "░" * (10 - int(cat_accuracy / 10))
        status = "✓" if cat_accuracy >= 80 else "⚠" if cat_accuracy >= 60 else "✗"
        print(f"  {cat:12s}: {stats['correct']:3d}/{stats['total']:3d} ({cat_accuracy:5.1f}%) {bar} [{status}]")

    # По стадиям поиска
    stages: Dict[str, int] = {}
    for r in results:
        stages[r.stage] = stages.get(r.stage, 0) + 1

    print("\nРаспределение по стадиям поиска:")
    for stage, count in sorted(stages.items(), key=lambda x: -x[1]):
        print(f"  {stage}: {count} ({count/total*100:.1f}%)")

    # Ошибки
    failures = [r for r in results if not r.is_correct]
    if failures:
        print(f"\n{'=' * 100}")
        print(f"ОШИБКИ ({len(failures)}):")
        print("-" * 100)
        for i, r in enumerate(failures[:50], 1):
            print(f"{i:2d}. {r.query[:60]}")
            print(f"    Ожидал: {r.expected_topic}")
            print(f"    Получил: {r.found_topic} (score={r.score:.2f}, stage={r.stage})")
        if len(failures) > 50:
            print(f"    ... и ещё {len(failures) - 50} ошибок")


def main():
    print("=" * 100)
    print("ТЕСТ ТОЧНОСТИ НОВЫХ СЕКЦИЙ 1300-1400")
    print("=" * 100)

    results = run_tests()
    print_summary(results)

    accuracy = sum(1 for r in results if r.is_correct) / len(results) * 100
    print(f"\nРезультат: {'PASSED' if accuracy >= 50 else 'FAILED'} ({accuracy:.1f}%)")

    return 0 if accuracy >= 50 else 1


if __name__ == "__main__":
    sys.exit(main())
