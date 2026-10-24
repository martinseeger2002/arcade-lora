/* LVGL settings for the host screenshot build: as close to the T-Deck's
   device-ui lv_conf.h as matters for drawing (16-bit colour, flex, widgets). */
#ifndef LV_CONF_H
#define LV_CONF_H
#define LV_COLOR_DEPTH 16
#define LV_USE_STDLIB_MALLOC LV_STDLIB_CLIB
#define LV_USE_STDLIB_STRING LV_STDLIB_CLIB
#define LV_USE_STDLIB_SPRINTF LV_STDLIB_CLIB
#define LV_USE_OS LV_OS_NONE
#define LV_USE_LOG 0
#define LV_FONT_MONTSERRAT_14 1
#define LV_FONT_DEFAULT &lv_font_montserrat_14
#define LV_USE_FLEX 1
#define LV_USE_GRID 1
#define LV_BUILD_EXAMPLES 0
#define LV_BUILD_DEMOS 0
#endif
