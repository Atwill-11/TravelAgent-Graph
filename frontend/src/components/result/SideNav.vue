<template>
  <div class="side-nav">
    <a-affix :offset-top="80">
      <a-menu
        mode="inline"
        :selected-keys="[activeSection]"
        @click="handleMenuClick"
      >
        <a-menu-item key="overview"><span>📋 行程概览</span></a-menu-item>
        <a-menu-item key="budget" v-if="hasBudget"
          ><span>💰 预算明细</span></a-menu-item
        >
        <a-menu-item key="map"><span>📍 景点地图</span></a-menu-item>
        <a-sub-menu key="days" title="📅 每日行程">
          <a-menu-item v-for="(day, index) in days" :key="`day-${index}`">
            第{{ day.day_index + 1 }}天
          </a-menu-item>
        </a-sub-menu>
        <a-menu-item key="weather" v-if="hasWeather">
          <span>🌤️ 天气信息</span>
        </a-menu-item>
      </a-menu>

      <slot name="review-panel"></slot>
    </a-affix>
  </div>
</template>

<script setup lang="ts">
import type { DayPlan, Budget, TravelWeatherData } from "@/types";

const props = defineProps<{
  activeSection: string;
  days: DayPlan[];
  budget?: Budget;
  weatherInfo?: TravelWeatherData;
}>();

const emit = defineEmits<{
  (e: "update:activeSection", value: string): void;
  (e: "scrollToSection", key: string): void;
}>();

const hasBudget = !!props.budget;
const hasWeather = props.weatherInfo && props.weatherInfo.weather.length > 0;

const handleMenuClick = ({ key }: { key: string }) => {
  emit("update:activeSection", key);
  emit("scrollToSection", key);
};
</script>

<style scoped>
.side-nav {
  width: 320px;
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

@media (max-width: 768px) {
  .side-nav {
    display: none;
  }
}
</style>
