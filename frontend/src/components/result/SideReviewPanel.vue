<template>
  <div v-if="visible" class="side-review-panel">
    <div class="side-review-header">
      <span>旅行计划审阅</span>
    </div>
    <div class="side-review-body">
      <p class="side-review-desc">您的旅行计划已生成，请审阅后选择操作：</p>
      <a-textarea
        v-model:value="reviewFeedback"
        placeholder="请输入修改意见（如：我要新增一天的旅游计划、换一个酒店等）..."
        :rows="3"
        class="side-review-input"
        :disabled="isModifying"
      />
      <div class="side-review-actions">
        <a-button
          type="primary"
          block
          :loading="isResuming"
          :disabled="isModifying"
          @click="handleCompletePlan"
        >
          ✅ 完成旅行规划
        </a-button>
        <a-button
          block
          :loading="isResuming"
          :disabled="!reviewFeedback.trim() || isModifying"
          @click="handleModifyPlan"
        >
          ✏️ 提交修改意见
        </a-button>
      </div>
    </div>

    <div v-if="isModifying" class="side-thinking-panel">
      <div class="side-thinking-header">
        <span>🤖 智能体修改思考过程</span>
      </div>
      <div class="side-thinking-body">
        <a-timeline>
          <a-timeline-item
            v-for="step in thinkingSteps"
            :key="step.id"
            :color="getStepColor(step.status)"
          >
            <div class="thinking-step">
              <span class="step-icon">{{ step.icon }}</span>
              <span class="step-name">{{ step.display_name }}</span>
              <a-spin v-if="step.status === 'running'" size="small" />
              <a-tag v-if="step.status === 'completed'" color="green" size="small"
                >完成</a-tag
              >
            </div>
            <div v-if="step.plan_items && step.plan_items.length > 0" class="step-plan-items">
              <a-tag
                v-for="item in step.plan_items"
                :key="item.task"
                color="blue"
                size="small"
              >
                {{ item.icon }} {{ item.type_display }}: {{ item.task }}
              </a-tag>
            </div>
          </a-timeline-item>
        </a-timeline>
        <div v-if="modifyError" class="thinking-error">
          <a-alert :message="modifyError" type="error" show-icon />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from "vue";
import { message } from "ant-design-vue";
import type { TripPlan, ThinkingStep } from "@/types";
import { resumeTripPlanStream } from "@/services/api";

const props = defineProps<{
  visible: boolean;
  tripPlan: TripPlan | null;
}>();

const emit = defineEmits<{
  (e: "update:visible", value: boolean): void;
  (e: "update:tripPlan", value: TripPlan): void;
  (e: "completed"): void;
}>();

const reviewFeedback = ref("");
const isResuming = ref(false);
const isModifying = ref(false);
const thinkingSteps = ref<ThinkingStep[]>([]);
const modifyError = ref<string>("");

watch(
  () => props.visible,
  (val) => {
    if (!val) {
      reviewFeedback.value = "";
      isModifying.value = false;
      thinkingSteps.value = [];
      modifyError.value = "";
    }
  }
);

const getStepColor = (status: string): string => {
  switch (status) {
    case "completed":
      return "green";
    case "running":
      return "blue";
    case "failed":
      return "red";
    default:
      return "gray";
  }
};

const addThinkingStep = (step: ThinkingStep) => {
  const existing = thinkingSteps.value.find(
    (s) => s.node === step.node && step.node !== "execute"
  );
  if (existing) {
    Object.assign(existing, step);
  } else {
    thinkingSteps.value.push(step);
  }
};

const updateLastStepStatus = (status: "completed" | "failed") => {
  if (thinkingSteps.value.length > 0) {
    thinkingSteps.value[thinkingSteps.value.length - 1].status = status;
  }
};

const handleCompletePlan = async () => {
  isResuming.value = true;
  modifyError.value = "";
  try {
    await resumeTripPlanStream(
      { action: "complete" },
      {
        onDone: () => {
          emit("update:visible", false);
          isResuming.value = false;
          emit("completed");
          message.success("旅行规划已完成！");
        },
        onError: (data) => {
          modifyError.value = data.message;
          isResuming.value = false;
          message.error(data.message);
        },
      }
    );
  } catch (error: any) {
    modifyError.value = error.message || "完成规划失败";
    isResuming.value = false;
  }
};

const handleModifyPlan = async () => {
  if (!reviewFeedback.value.trim()) return;

  isResuming.value = true;
  isModifying.value = true;
  modifyError.value = "";
  thinkingSteps.value = [];

  const feedback = reviewFeedback.value.trim();

  try {
    await resumeTripPlanStream(
      { action: "modify", feedback },
      {
        onStart: () => {
          addThinkingStep({
            id: `start-${Date.now()}`,
            node: "start",
            display_name: "开始修改",
            icon: "🚀",
            message: "正在根据您的意见修改旅行计划...",
            status: "running",
            timestamp: Date.now(),
          });
        },
        onPlan: (data) => {
          updateLastStepStatus("completed");
          addThinkingStep({
            id: `plan-${Date.now()}`,
            node: "plan",
            display_name: data.display_name,
            icon: data.icon,
            message: data.message,
            status: "running",
            timestamp: Date.now(),
            plan_items: data.plan_items,
          });
        },
        onExecute: (data) => {
          updateLastStepStatus("completed");
          addThinkingStep({
            id: `execute-${Date.now()}`,
            node: "execute",
            display_name: data.display_name,
            icon: data.icon,
            message: data.message,
            status: "running",
            timestamp: Date.now(),
          });
        },
        onSummarize: (data) => {
          updateLastStepStatus("completed");
          addThinkingStep({
            id: `summarize-${Date.now()}`,
            node: "summarize",
            display_name: data.display_name,
            icon: data.icon,
            message: data.message,
            status: "running",
            timestamp: Date.now(),
          });
          if (data.trip_plan) {
            emit("update:tripPlan", data.trip_plan);
          }
        },
        onReview: (data) => {
          updateLastStepStatus("completed");
          addThinkingStep({
            id: `review-${Date.now()}`,
            node: "user_review",
            display_name: data.display_name,
            icon: data.icon,
            message: data.message,
            status: "completed",
            timestamp: Date.now(),
          });
          if (data.trip_plan) {
            emit("update:tripPlan", data.trip_plan);
          }
          if (!data.user_decision) {
            isResuming.value = false;
            isModifying.value = false;
          }
        },
        onDone: () => {
          updateLastStepStatus("completed");
          isResuming.value = false;
          isModifying.value = false;
          emit("completed");
          message.success("旅行计划修改完成！");
        },
        onError: (data) => {
          updateLastStepStatus("failed");
          modifyError.value = data.message;
          isResuming.value = false;
          message.error(data.message);
        },
      }
    );
  } catch (error: any) {
    modifyError.value = error.message || "修改规划失败";
    isResuming.value = false;
  }
};
</script>

<style scoped>
.side-review-panel {
  margin-top: 16px;
  background: white;
  border-radius: 12px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
  overflow: hidden;
}

.side-review-header {
  padding: 12px 16px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  font-weight: 600;
  font-size: 14px;
}

.side-review-body {
  padding: 16px;
}

.side-review-desc {
  margin: 0 0 12px 0;
  font-size: 13px;
  color: #666;
  line-height: 1.5;
}

.side-review-input {
  margin-bottom: 12px;
}

.side-review-actions {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.side-thinking-panel {
  margin-top: 16px;
  margin-left: 8px;
  border-top: 1px solid #f0f0f0;
  padding-top: 16px;
}

.side-thinking-header {
  font-weight: 600;
  font-size: 13px;
  color: #333;
  margin-bottom: 12px;
}

.side-thinking-body {
  max-height: 300px;
  overflow-y: auto;
}

.side-thinking-body :deep(.ant-timeline) {
  font-size: 12px;
}

.side-thinking-body :deep(.ant-timeline-item-content) {
  padding-bottom: 8px;
}

.side-thinking-body .thinking-step {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.side-thinking-body .step-icon {
  font-size: 14px;
}

.side-thinking-body .step-name {
  font-weight: 500;
  color: #333;
}

.side-thinking-body .step-plan-items {
  margin-top: 4px;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.side-thinking-body .thinking-error {
  margin-top: 8px;
}
</style>
