<template>
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
</template>

<script setup lang="ts">
import { marked } from "marked";
import type { TripPlan } from "@/types";

defineProps<{
  tripPlan: TripPlan;
}>();

const renderMarkdown = (text: string): string => {
  if (!text) return "";
  return marked(text) as string;
};
</script>

<style scoped>
.overview-card {
  border-radius: 16px;
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.08);
  transition: all 0.3s ease;
}

.overview-card:hover {
  box-shadow: 0 8px 28px rgba(102, 126, 234, 0.15);
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
</style>
