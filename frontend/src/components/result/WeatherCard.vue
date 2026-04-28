<template>
  <a-card
    id="weather"
    v-if="weatherInfo && weatherInfo.weather.length > 0"
    title="🌤️ 天气信息"
    style="margin-top: 20px"
    :bordered="false"
  >
    <div v-if="weatherInfo.travel_advice" class="weather-advice">
      <a-alert
        :message="weatherInfo.travel_advice"
        type="info"
        show-icon
      />
    </div>
    <a-list
      :data-source="weatherInfo.weather"
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
    <div v-if="weatherInfo.air_quality" style="margin-top: 16px">
      <a-descriptions title="🌬️ 空气质量" bordered size="small" :column="3">
        <a-descriptions-item label="AQI">{{
          weatherInfo.air_quality.aqi
        }}</a-descriptions-item>
        <a-descriptions-item label="类别">{{
          weatherInfo.air_quality.category
        }}</a-descriptions-item>
        <a-descriptions-item label="主要污染物">{{
          weatherInfo.air_quality.primary_pollutant || "-"
        }}</a-descriptions-item>
        <a-descriptions-item label="PM2.5">{{
          weatherInfo.air_quality.pm25
        }}</a-descriptions-item>
        <a-descriptions-item label="PM10">{{
          weatherInfo.air_quality.pm10
        }}</a-descriptions-item>
        <a-descriptions-item label="健康建议">{{
          weatherInfo.air_quality.health_advice || "-"
        }}</a-descriptions-item>
      </a-descriptions>
    </div>
  </a-card>
</template>

<script setup lang="ts">
import type { TravelWeatherData } from "@/types";

defineProps<{
  weatherInfo?: TravelWeatherData;
}>();
</script>

<style scoped>
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
</style>
