<template>
  <div class="result-container">
    <div class="page-header">
      <a-button class="back-button" size="large" @click="goBack"
        >← 返回首页</a-button
      >
    </div>

    <div v-if="tripPlan" class="content-wrapper">
      <SideNav
        :active-section="activeSection"
        :days="tripPlan.days"
        :budget="tripPlan.budget"
        :weather-info="tripPlan.weather_info"
        @update:active-section="activeSection = $event"
        @scroll-to-section="scrollToSection"
      >
        <template #review-panel>
          <SideReviewPanel
            :visible="reviewModalVisible"
            :trip-plan="tripPlan"
            @update:visible="reviewModalVisible = $event"
            @update:trip-plan="handleTripPlanUpdate"
            @completed="handleReviewCompleted"
          />
        </template>
      </SideNav>

      <div class="main-content">
        <MapCard :trip-plan="tripPlan" />

        <div class="info-section">
          <OverviewCard :trip-plan="tripPlan" />
          <BudgetCard :budget="tripPlan.budget" />
        </div>

        <DaysCard :days="tripPlan.days" v-model:active-days="activeDays" />

        <WeatherCard :weather-info="tripPlan.weather_info" />
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
import { ref, onMounted } from "vue";
import { useRouter } from "vue-router";
import type { TripPlan } from "@/types";
import {
  SideNav,
  SideReviewPanel,
  MapCard,
  OverviewCard,
  BudgetCard,
  DaysCard,
  WeatherCard,
} from "@/components/result";

const router = useRouter();
const tripPlan = ref<TripPlan | null>(null);
const activeSection = ref("overview");
const activeDays = ref<number[]>([0]);
const reviewModalVisible = ref(false);

onMounted(async () => {
  const data = sessionStorage.getItem("tripPlan");
  if (data) {
    tripPlan.value = JSON.parse(data);
  }

  const needsReview = sessionStorage.getItem("needsReview");
  if (needsReview === "true") {
    setTimeout(() => {
      reviewModalVisible.value = true;
    }, 500);
  }
});

const handleTripPlanUpdate = (newPlan: TripPlan) => {
  tripPlan.value = newPlan;
  sessionStorage.setItem("tripPlan", JSON.stringify(newPlan));
};

const handleReviewCompleted = () => {
  sessionStorage.removeItem("needsReview");
};

const goBack = () => {
  router.push("/");
};

const scrollToSection = (key: string) => {
  activeSection.value = key;
  const element = document.getElementById(key);
  if (element) {
    element.scrollIntoView({ behavior: "smooth", block: "start" });
  }
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

.main-content {
  flex: 1;
  min-width: 0;
}

.info-section {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
  gap: 24px;
  margin-bottom: 24px;
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
}

@media (max-width: 768px) {
  .result-container {
    padding: 20px 12px;
  }

  .content-wrapper {
    max-width: 100%;
  }

  .info-section {
    grid-template-columns: 1fr;
  }
}
</style>
