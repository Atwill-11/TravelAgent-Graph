<template>
  <a-card
    id="budget"
    v-if="budget"
    title="💰 预算明细"
    :bordered="false"
    class="budget-card"
  >
    <div class="budget-grid">
      <div class="budget-item">
        <div class="budget-icon">🎫</div>
        <div class="budget-label">景点门票</div>
        <div class="budget-value">¥{{ budget.total_attractions }}</div>
      </div>
      <div class="budget-item">
        <div class="budget-icon">🏨</div>
        <div class="budget-label">酒店住宿</div>
        <div class="budget-value">¥{{ budget.total_hotels }}</div>
      </div>
      <div class="budget-item">
        <div class="budget-icon">🍽️</div>
        <div class="budget-label">餐饮费用</div>
        <div class="budget-value">¥{{ budget.total_meals }}</div>
      </div>
      <div class="budget-item">
        <div class="budget-icon">🚗</div>
        <div class="budget-label">交通费用</div>
        <div class="budget-value">¥{{ budget.total_transportation }}</div>
      </div>
    </div>
    <div class="budget-total">
      <span class="total-label">预估总费用</span>
      <span class="total-value">¥{{ budget.total }}</span>
    </div>
  </a-card>
</template>

<script setup lang="ts">
import type { Budget } from "@/types";

defineProps<{
  budget?: Budget;
}>();
</script>

<style scoped>
.budget-card {
  border-radius: 16px;
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.08);
  transition: all 0.3s ease;
}

.budget-card:hover {
  box-shadow: 0 8px 28px rgba(102, 126, 234, 0.15);
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

@media (max-width: 768px) {
  .budget-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
