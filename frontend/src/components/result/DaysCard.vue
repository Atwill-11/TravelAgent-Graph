<template>
  <a-card title="📅 每日行程" :bordered="false" class="days-card">
    <a-collapse v-model:activeKey="activeDays" accordion>
      <a-collapse-panel
        v-for="(day, index) in days"
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
                <span class="detail-text">{{ item.visit_duration }}分钟</span>
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

        <a-divider v-if="day.hotel" orientation="left">🏨 住宿推荐</a-divider>
        <a-card v-if="day.hotel" size="small" class="hotel-card">
          <template #header>
            <span class="hotel-title">{{ day.hotel.name }}</span>
          </template>
          <a-descriptions :column="2" size="small">
            <a-descriptions-item label="地址">{{
              day.hotel.address
            }}</a-descriptions-item>
            <a-descriptions-item label="类型">{{
              day.hotel.hotel_type || "-"
            }}</a-descriptions-item>
            <a-descriptions-item label="最低价格">{{
              day.hotel.lowest_price ? `¥${day.hotel.lowest_price}/晚` : "-"
            }}</a-descriptions-item>
            <a-descriptions-item label="评分">{{
              day.hotel.rating ? `${day.hotel.rating}⭐` : "-"
            }}</a-descriptions-item>
            <a-descriptions-item label="距离" :span="2">{{
              day.hotel.distance || "-"
            }}</a-descriptions-item>
          </a-descriptions>
        </a-card>

        <a-divider v-if="day.meals && day.meals.length > 0" orientation="left"
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
</template>

<script setup lang="ts">
import { ref, watch } from "vue";
import type { DayPlan } from "@/types";

const props = defineProps<{
  days: DayPlan[];
  initialActiveDays?: number[];
}>();

const emit = defineEmits<{
  (e: "update:activeDays", value: number[]): void;
}>();

const activeDays = ref<number[]>(props.initialActiveDays || [0]);

watch(activeDays, (val) => {
  emit("update:activeDays", val);
});

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
  const colors = ["#e6f7ff", "#f6ffed", "#fff7e6", "#fff1f0", "#f9f0ff"];
  const colorIndex = index % colors.length;
  const bgColor = colors[colorIndex];
  const textColors = ["#1890ff", "#52c41a", "#fa8c16", "#f5222d", "#722ed1"];
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
      '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300"><rect width="400" height="300" fill="#e8e8e8"/><text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" font-family="sans-serif" font-size="18" fill="#999">暂无图片</text></svg>'
    );
};
</script>

<style scoped>
.days-card {
  border-radius: 16px;
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.08);
  transition: all 0.3s ease;
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

@media (max-width: 768px) {
  .attractions-grid {
    grid-template-columns: 1fr;
  }
}
</style>
