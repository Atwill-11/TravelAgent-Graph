<template>
  <div class="result-container">
    <div class="page-header">
      <a-button class="back-button" size="large" @click="goBack"
        >← 返回首页</a-button
      >
    </div>

    <div v-if="tripPlan" class="content-wrapper">
      <div class="side-nav">
        <a-affix :offset-top="80">
          <a-menu
            mode="inline"
            :selected-keys="[activeSection]"
            @click="scrollToSection"
          >
            <a-menu-item key="overview"><span>📋 行程概览</span></a-menu-item>
            <a-menu-item key="budget" v-if="tripPlan.budget"
              ><span>💰 预算明细</span></a-menu-item
            >
            <a-menu-item key="map"><span>📍 景点地图</span></a-menu-item>
            <a-sub-menu key="days" title="📅 每日行程">
              <a-menu-item
                v-for="(day, index) in tripPlan.days"
                :key="`day-${index}`"
              >
                第{{ day.day_index + 1 }}天
              </a-menu-item>
            </a-sub-menu>
            <a-menu-item
              key="weather"
              v-if="
                tripPlan.weather_info &&
                tripPlan.weather_info.weather.length > 0
              "
            >
              <span>🌤️ 天气信息</span>
            </a-menu-item>
          </a-menu>
        </a-affix>
      </div>

      <div class="main-content">
        <a-card
          id="map"
          title="📍 景点地图"
          :bordered="false"
          class="map-card"
        >
          <div id="amap-container" style="width: 100%; height: 100%"></div>
        </a-card>

        <div class="info-section">
          <a-card
            id="overview"
            :title="`${tripPlan.city}旅行计划`"
            :bordered="false"
            class="overview-card"
          >
            <div class="overview-content">
              <div class="info-item">
                <span class="info-label">📅 日期:</span>
                <span class="info-value"
                  >{{ tripPlan.start_date }} 至 {{ tripPlan.end_date }}</span
                >
              </div>
              <div class="info-item">
                <span class="info-label">💡 建议:</span>
                <span
                  class="info-value markdown-content"
                  v-html="renderMarkdown(tripPlan.overall_suggestions)"
                ></span>
              </div>
            </div>
          </a-card>

          <a-card
            id="budget"
            v-if="tripPlan.budget"
            title="💰 预算明细"
            :bordered="false"
            class="budget-card"
          >
            <div class="budget-grid">
              <div class="budget-item">
                <div class="budget-icon">🎫</div>
                <div class="budget-label">景点门票</div>
                <div class="budget-value">
                  ¥{{ tripPlan.budget.total_attractions }}
                </div>
              </div>
              <div class="budget-item">
                <div class="budget-icon">🏨</div>
                <div class="budget-label">酒店住宿</div>
                <div class="budget-value">
                  ¥{{ tripPlan.budget.total_hotels }}
                </div>
              </div>
              <div class="budget-item">
                <div class="budget-icon">🍽️</div>
                <div class="budget-label">餐饮费用</div>
                <div class="budget-value">
                  ¥{{ tripPlan.budget.total_meals }}
                </div>
              </div>
              <div class="budget-item">
                <div class="budget-icon">🚗</div>
                <div class="budget-label">交通费用</div>
                <div class="budget-value">
                  ¥{{ tripPlan.budget.total_transportation }}
                </div>
              </div>
            </div>
            <div class="budget-total">
              <span class="total-label">预估总费用</span>
              <span class="total-value">¥{{ tripPlan.budget.total }}</span>
            </div>
          </a-card>
        </div>

        <a-card title="📅 每日行程" :bordered="false" class="days-card">
          <a-collapse v-model:activeKey="activeDays" accordion>
            <a-collapse-panel
              v-for="(day, index) in tripPlan.days"
              :key="index"
              :id="`day-${index}`"
            >
              <template #header>
                <div class="day-header">
                  <span class="day-title">第{{ day.day_index + 1 }}天</span>
                  <span class="day-date">{{ day.date }}</span>
                </div>
              </template>

              <div class="day-info">
                <div class="info-row">
                  <span class="label">📝 行程描述:</span>
                  <span class="value">{{ day.description }}</span>
                </div>
                <div class="info-row">
                  <span class="label">🚗 交通方式:</span>
                  <span class="value">{{ day.transportation }}</span>
                </div>
                <div class="info-row">
                  <span class="label">🏨 住宿:</span>
                  <span class="value">{{ day.accommodation }}</span>
                </div>
              </div>

              <a-divider orientation="left">🎯 景点安排</a-divider>
              <div class="attractions-grid">
                <a-card
                  v-for="(item, attrIndex) in day.attractions"
                  :key="attrIndex"
                  size="small"
                  class="attraction-card"
                >
                  <div class="attraction-image-wrapper">
                    <img
                      :src="getAttractionImage(item.name, attrIndex)"
                      :alt="item.name"
                      class="attraction-image"
                      @error="handleImageError"
                    />
                    <div class="attraction-badge">
                      <span class="badge-number">{{ attrIndex + 1 }}</span>
                    </div>
                    <div v-if="item.ticket_price" class="price-tag">
                      ¥{{ item.ticket_price }}
                    </div>
                  </div>
                  <div class="attraction-info">
                    <h4 class="attraction-name">{{ item.name }}</h4>
                    <div class="attraction-detail">
                      <span class="detail-icon">📍</span>
                      <span class="detail-text">{{ item.address }}</span>
                    </div>
                    <div class="attraction-detail">
                      <span class="detail-icon">⏱️</span>
                      <span class="detail-text"
                        >{{ item.visit_duration }}分钟</span
                      >
                    </div>
                    <div v-if="item.rating" class="attraction-detail">
                      <span class="detail-icon">⭐</span>
                      <span class="detail-text">{{ item.rating }}</span>
                    </div>
                    <div v-if="item.open_time" class="attraction-detail">
                      <span class="detail-icon">🕐</span>
                      <span class="detail-text">{{ item.open_time }}</span>
                    </div>
                    <div v-if="item.description" class="attraction-description">
                      {{ item.description }}
                    </div>
                  </div>
                </a-card>
              </div>

              <a-divider v-if="day.hotel" orientation="left"
                >🏨 住宿推荐</a-divider
              >
              <a-card v-if="day.hotel" size="small" class="hotel-card">
                <template #title
                  ><span class="hotel-title">{{
                    day.hotel.name
                  }}</span></template
                >
                <a-descriptions :column="2" size="small">
                  <a-descriptions-item label="地址">{{
                    day.hotel.address
                  }}</a-descriptions-item>
                  <a-descriptions-item label="类型">{{
                    day.hotel.hotel_type || "-"
                  }}</a-descriptions-item>
                  <a-descriptions-item label="最低价格">{{
                    day.hotel.lowest_price
                      ? `¥${day.hotel.lowest_price}/晚`
                      : "-"
                  }}</a-descriptions-item>
                  <a-descriptions-item label="评分">{{
                    day.hotel.rating ? `${day.hotel.rating}⭐` : "-"
                  }}</a-descriptions-item>
                  <a-descriptions-item label="距离" :span="2">{{
                    day.hotel.distance || "-"
                  }}</a-descriptions-item>
                </a-descriptions>
              </a-card>

              <a-divider
                v-if="day.meals && day.meals.length > 0"
                orientation="left"
                >🍽️ 餐饮安排</a-divider
              >
              <a-descriptions
                v-if="day.meals && day.meals.length > 0"
                :column="1"
                bordered
                size="small"
              >
                <a-descriptions-item
                  v-for="meal in day.meals"
                  :key="meal.type"
                  :label="getMealLabel(meal.type)"
                >
                  {{ meal.name }}
                  <span v-if="meal.description"> - {{ meal.description }}</span>
                </a-descriptions-item>
              </a-descriptions>
            </a-collapse-panel>
          </a-collapse>
        </a-card>

        <a-card
          id="weather"
          v-if="
            tripPlan.weather_info && tripPlan.weather_info.weather.length > 0
          "
          title="🌤️ 天气信息"
          style="margin-top: 20px"
          :bordered="false"
        >
          <div
            v-if="tripPlan.weather_info.travel_advice"
            class="weather-advice"
          >
            <a-alert
              :message="tripPlan.weather_info.travel_advice"
              type="info"
              show-icon
            />
          </div>
          <a-list
            :data-source="tripPlan.weather_info.weather"
            :grid="{ gutter: 16, column: 3 }"
            style="margin-top: 16px"
          >
            <template #renderItem="{ item }">
              <a-list-item>
                <a-card size="small" class="weather-card">
                  <div class="weather-date">{{ item.date }}</div>
                  <div class="weather-info-row">
                    <span class="weather-icon">☀️</span>
                    <div>
                      <div class="weather-label">白天</div>
                      <div class="weather-value">
                        {{ item.text_day }} {{ item.temp_max }}°C
                      </div>
                    </div>
                  </div>
                  <div class="weather-info-row">
                    <span class="weather-icon">🌙</span>
                    <div>
                      <div class="weather-label">夜间</div>
                      <div class="weather-value">
                        {{ item.text_night }} {{ item.temp_min }}°C
                      </div>
                    </div>
                  </div>
                  <div class="weather-wind">
                    💨 {{ item.wind_dir }} {{ item.wind_scale }}级
                  </div>
                  <div class="weather-extra">💧 湿度: {{ item.humidity }}%</div>
                </a-card>
              </a-list-item>
            </template>
          </a-list>
          <div
            v-if="tripPlan.weather_info.air_quality"
            style="margin-top: 16px"
          >
            <a-descriptions
              title="🌬️ 空气质量"
              bordered
              size="small"
              :column="3"
            >
              <a-descriptions-item label="AQI">{{
                tripPlan.weather_info.air_quality.aqi
              }}</a-descriptions-item>
              <a-descriptions-item label="类别">{{
                tripPlan.weather_info.air_quality.category
              }}</a-descriptions-item>
              <a-descriptions-item label="主要污染物">{{
                tripPlan.weather_info.air_quality.primary_pollutant || "-"
              }}</a-descriptions-item>
              <a-descriptions-item label="PM2.5">{{
                tripPlan.weather_info.air_quality.pm25
              }}</a-descriptions-item>
              <a-descriptions-item label="PM10">{{
                tripPlan.weather_info.air_quality.pm10
              }}</a-descriptions-item>
              <a-descriptions-item label="健康建议">{{
                tripPlan.weather_info.air_quality.health_advice || "-"
              }}</a-descriptions-item>
            </a-descriptions>
          </div>
        </a-card>
      </div>
    </div>

    <a-empty v-else description="没有找到旅行计划数据">
      <template #image><div style="font-size: 80px">🗺️</div></template>
      <template #description
        ><span style="color: #999"
          >暂无旅行计划数据，请先创建行程</span
        ></template
      >
      <a-button type="primary" @click="goBack">返回首页创建行程</a-button>
    </a-empty>

    <a-back-top :visibility-height="300">
      <div class="back-top-button">↑</div>
    </a-back-top>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick, onBeforeUnmount } from "vue";
import { useRouter } from "vue-router";
import { message } from "ant-design-vue";
import AMapLoader from "@amap/amap-jsapi-loader";
import { marked } from "marked";
import type { TripPlan } from "@/types";

const router = useRouter();
const tripPlan = ref<TripPlan | null>(null);
const activeSection = ref("overview");
const activeDays = ref<number[]>([0]);
let map: any = null;

onMounted(async () => {
  const data = sessionStorage.getItem("tripPlan");
  if (data) {
    tripPlan.value = JSON.parse(data);
    await nextTick();
    initMap();
  }
});

onBeforeUnmount(() => {
  if (map) {
    map.destroy();
    map = null;
  }
});

const goBack = () => {
  router.push("/");
};

const scrollToSection = ({ key }: { key: string }) => {
  activeSection.value = key;
  const element = document.getElementById(key);
  if (element) {
    element.scrollIntoView({ behavior: "smooth", block: "start" });
  }
};

const getMealLabel = (type: string): string => {
  const labels: Record<string, string> = {
    breakfast: "早餐",
    lunch: "午餐",
    dinner: "晚餐",
    snack: "小吃",
  };
  return labels[type] || type;
};

const getAttractionImage = (name: string, index: number): string => {
  const colors = [
    "#e6f7ff",
    "#f6ffed",
    "#fff7e6",
    "#fff1f0",
    "#f9f0ff",
  ];
  const colorIndex = index % colors.length;
  const bgColor = colors[colorIndex];
  const textColors = [
    "#1890ff",
    "#52c41a",
    "#fa8c16",
    "#f5222d",
    "#722ed1",
  ];
  const textColor = textColors[colorIndex];

  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300">
    <rect width="400" height="300" fill="${bgColor}"/>
    <text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" font-family="sans-serif" font-size="20" font-weight="600" fill="${textColor}">${name}</text>
  </svg>`;

  return `data:image/svg+xml;base64,${btoa(unescape(encodeURIComponent(svg)))}`;
};

const handleImageError = (event: Event) => {
  const img = event.target as HTMLImageElement;
  img.src =
    "data:image/svg+xml;base64," +
    btoa(
      '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300"><rect width="400" height="300" fill="#e8e8e8"/><text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" font-family="sans-serif" font-size="18" fill="#999">暂无图片</text></svg>',
    );
};

const initMap = async () => {
  try {
    const AMap = await AMapLoader.load({
      key: import.meta.env.VITE_AMAP_WEB_JS_KEY,
      version: "2.0",
      plugins: ["AMap.Marker", "AMap.Polyline", "AMap.InfoWindow"],
    });

    map = new AMap.Map("amap-container", {
      zoom: 12,
      center: [116.397128, 39.916527],
      viewMode: "3D",
    });

    addAttractionMarkers(AMap);
    message.success("地图加载成功");
  } catch (error) {
    console.error("地图加载失败:", error);
    message.error("地图加载失败，请检查高德地图Key配置");
  }
};

const addAttractionMarkers = (AMap: any) => {
  if (!tripPlan.value) return;

  const markers: any[] = [];
  const allAttractions: any[] = [];

  tripPlan.value.days.forEach((day, dayIndex) => {
    day.attractions.forEach((attraction, attrIndex) => {
      if (
        attraction.location &&
        attraction.location.longitude &&
        attraction.location.latitude
      ) {
        allAttractions.push({
          ...attraction,
          dayIndex,
          attrIndex,
        });
      }
    });
  });

  allAttractions.forEach((attraction, index) => {
    const marker = new AMap.Marker({
      position: [attraction.location.longitude, attraction.location.latitude],
      title: attraction.name,
      label: {
        content: `<div style="background: #4CAF50; color: white; padding: 4px 8px; border-radius: 4px; font-size: 12px;">${index + 1}</div>`,
        offset: new AMap.Pixel(0, -30),
      },
    });

    const infoWindow = new AMap.InfoWindow({
      content: `
        <div style="padding: 10px;">
          <h4 style="margin: 0 0 8px 0;">${attraction.name}</h4>
          <p style="margin: 4px 0;"><strong>地址:</strong> ${attraction.address}</p>
          <p style="margin: 4px 0;"><strong>游览时长:</strong> ${attraction.visit_duration}分钟</p>
          ${attraction.description ? `<p style="margin: 4px 0;"><strong>描述:</strong> ${attraction.description}</p>` : ""}
          <p style="margin: 4px 0; color: #1890ff;"><strong>第${attraction.dayIndex + 1}天 景点${attraction.attrIndex + 1}</strong></p>
        </div>
      `,
      offset: new AMap.Pixel(0, -30),
    });

    marker.on("click", () => {
      infoWindow.open(map, marker.getPosition());
    });

    markers.push(marker);
  });

  map.add(markers);

  if (allAttractions.length > 0) {
    map.setFitView(markers);
  }

  drawRoutes(AMap, allAttractions);
};

const drawRoutes = (AMap: any, attractions: any[]) => {
  if (attractions.length < 2) return;

  const dayGroups: any = {};
  attractions.forEach((attr) => {
    if (!dayGroups[attr.dayIndex]) {
      dayGroups[attr.dayIndex] = [];
    }
    dayGroups[attr.dayIndex].push(attr);
  });

  const dayColors = ["#1890ff", "#52c41a", "#faad14", "#f5222d", "#722ed1"];

  Object.entries(dayGroups).forEach(
    ([dayKey, dayAttractions]: [string, any]) => {
      if (dayAttractions.length < 2) return;

      const path = dayAttractions.map((attr: any) => [
        attr.location.longitude,
        attr.location.latitude,
      ]);

      const dayIndex = parseInt(dayKey);
      const polyline = new AMap.Polyline({
        path: path,
        strokeColor: dayColors[dayIndex % dayColors.length],
        strokeWeight: 4,
        strokeOpacity: 0.8,
        strokeStyle: "solid",
        showDir: true,
      });

      map.add(polyline);
    },
  );
};

const renderMarkdown = (text: string): string => {
  if (!text) return "";
  return marked(text) as string;
};
</script>

<style scoped>
.result-container {
  min-height: calc(100vh - 64px - 69px);
  background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
  padding: 40px 20px;
}

.page-header {
  max-width: 1200px;
  margin: 0 auto 30px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  animation: fadeInDown 0.6s ease-out;
}

.back-button {
  border-radius: 8px;
  font-weight: 500;
}

.content-wrapper {
  max-width: 1400px;
  margin: 0 auto;
  display: flex;
  gap: 24px;
}

.side-nav {
  width: 240px;
  flex-shrink: 0;
}

.side-nav :deep(.ant-menu) {
  border-radius: 12px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
  background: white;
}

.side-nav :deep(.ant-menu-item) {
  margin: 4px 8px;
  border-radius: 8px;
  transition: all 0.3s ease;
}

.side-nav :deep(.ant-menu-item-selected) {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
}

.side-nav :deep(.ant-menu-item:hover) {
  background: rgba(102, 126, 234, 0.1);
}

.main-content {
  flex: 1;
  min-width: 0;
}

.map-card {
  border-radius: 16px;
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.08);
  transition: all 0.3s ease;
  height: 400px;
  margin-bottom: 24px;
}

.map-card :deep(.ant-card-body) {
  height: calc(100% - 57px);
  padding: 0;
}

#amap-container {
  border-radius: 0 0 16px 16px;
}

.info-section {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
  gap: 24px;
  margin-bottom: 24px;
}

.overview-card,
.budget-card,
.days-card {
  border-radius: 16px;
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.08);
  transition: all 0.3s ease;
}

.overview-card:hover,
.budget-card:hover {
  box-shadow: 0 8px 28px rgba(102, 126, 234, 0.15);
}

.map-card {
  height: 480px;
}

.map-card :deep(.ant-card-body) {
  height: calc(100% - 57px);
  padding: 0;
}

#amap-container {
  border-radius: 0 0 12px 12px;
}

.overview-content {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.info-item {
  display: flex;
  gap: 8px;
}
.info-label {
  font-weight: 600;
  color: #555;
  white-space: nowrap;
}
.info-value {
  color: #333;
}

.budget-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  margin-bottom: 16px;
}

.budget-item {
  text-align: center;
  padding: 16px 12px;
  background: linear-gradient(135deg, #f8f9ff 0%, #fff 100%);
  border-radius: 12px;
  border: 1px solid rgba(102, 126, 234, 0.1);
  transition: all 0.3s ease;
}

.budget-item:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.15);
}

.budget-icon {
  font-size: 24px;
  margin-bottom: 8px;
}

.budget-label {
  font-size: 13px;
  color: #666;
  margin-bottom: 6px;
}
.budget-value {
  font-size: 22px;
  font-weight: 700;
  color: #667eea;
}

.budget-total {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-radius: 8px;
  color: white;
}

.total-label {
  font-size: 16px;
}
.total-value {
  font-size: 24px;
  font-weight: 700;
}

.day-header {
  display: flex;
  align-items: center;
  gap: 12px;
}
.day-title {
  font-weight: 600;
  font-size: 16px;
}
.day-date {
  color: #888;
  font-size: 14px;
}

.day-info {
  margin-bottom: 16px;
}
.info-row {
  margin-bottom: 8px;
}
.info-row .label {
  font-weight: 600;
  color: #555;
}
.info-row .value {
  color: #333;
}

.attractions-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 20px;
  margin-top: 16px;
}

.attraction-card {
  border-radius: 12px;
  transition: all 0.3s ease;
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
  border: 1px solid #e8e8e8;
  background: #ffffff;
}

.attraction-card :deep(.ant-card-body) {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 0;
}

.attraction-card:hover {
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
  transform: translateY(-4px);
  border-color: #d9d9d9;
}

.attraction-info {
  padding: 16px;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.attraction-name {
  margin: 0;
  font-size: 17px;
  font-weight: 600;
  color: #262626;
  line-height: 1.4;
}

.attraction-detail {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 14px;
  color: #595959;
  line-height: 1.5;
}

.detail-icon {
  flex-shrink: 0;
  font-size: 16px;
}

.detail-text {
  flex: 1;
}

.attraction-description {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid #f0f0f0;
  font-size: 13px;
  color: #8c8c8c;
  line-height: 1.6;
}

.attraction-image-wrapper {
  position: relative;
  height: 180px;
  overflow: hidden;
  background: #fafafa;
}

.attraction-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.attraction-badge {
  position: absolute;
  top: 8px;
  left: 8px;
  background: #52c41a;
  color: white;
  width: 26px;
  height: 26px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 600;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.15);
}

.price-tag {
  position: absolute;
  top: 8px;
  right: 8px;
  background: rgba(255, 255, 255, 0.95);
  color: #ff4d4f;
  padding: 4px 10px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 600;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  border: 1px solid #ffccc7;
}

.hotel-card {
  border-radius: 12px;
}
.hotel-title {
  font-weight: 600;
}

.weather-card {
  border-radius: 16px;
  text-align: center;
  transition: all 0.3s ease;
  border: 1px solid rgba(0, 0, 0, 0.06);
  overflow: hidden;
}

.weather-card:hover {
  box-shadow: 0 12px 32px rgba(102, 126, 234, 0.2);
  transform: translateY(-6px);
  border-color: rgba(102, 126, 234, 0.2);
}

.weather-date {
  font-weight: 600;
  font-size: 16px;
  margin-bottom: 16px;
  color: #333;
  padding: 12px;
  background: linear-gradient(135deg, #f8f9ff 0%, #fff 100%);
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
}

.weather-info-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  justify-content: center;
  padding: 8px;
}

.weather-icon {
  font-size: 28px;
}
.weather-label {
  font-size: 12px;
  color: #999;
  text-align: left;
}
.weather-value {
  font-size: 15px;
  font-weight: 600;
  color: #333;
  text-align: left;
}
.weather-wind {
  color: #666;
  font-size: 14px;
  margin-top: 12px;
  padding: 8px;
  background: rgba(102, 126, 234, 0.05);
  border-radius: 8px;
}
.weather-extra {
  color: #666;
  font-size: 14px;
  margin-top: 8px;
  padding: 8px;
  background: rgba(102, 126, 234, 0.05);
  border-radius: 8px;
}
.weather-advice {
  margin-bottom: 16px;
}

.back-top-button {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
}

.markdown-content {
  line-height: 1.6;
}

.markdown-content :deep(h1),
.markdown-content :deep(h2),
.markdown-content :deep(h3) {
  margin-top: 16px;
  margin-bottom: 8px;
  font-weight: 600;
}

.markdown-content :deep(p) {
  margin: 8px 0;
}

.markdown-content :deep(ul),
.markdown-content :deep(ol) {
  padding-left: 20px;
  margin: 8px 0;
}

.markdown-content :deep(li) {
  margin: 4px 0;
}

.markdown-content :deep(code) {
  background: #f5f5f5;
  padding: 2px 6px;
  border-radius: 4px;
  font-family: monospace;
}

.markdown-content :deep(strong) {
  font-weight: 600;
}

@keyframes fadeInDown {
  from {
    opacity: 0;
    transform: translateY(-30px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@media (max-width: 1400px) {
  .info-section {
    grid-template-columns: 1fr;
  }
  
  .map-card {
    height: 350px;
  }
}

@media (max-width: 768px) {
  .result-container {
    padding: 20px 12px;
  }
  
  .side-nav {
    display: none;
  }
  
  .content-wrapper {
    max-width: 100%;
  }
  
  .attractions-grid {
    grid-template-columns: 1fr;
  }
  
  .budget-grid {
    grid-template-columns: repeat(2, 1fr);
  }
  
  .info-section {
    grid-template-columns: 1fr;
  }
  
  .map-card {
    height: 300px;
  }
}
</style>
