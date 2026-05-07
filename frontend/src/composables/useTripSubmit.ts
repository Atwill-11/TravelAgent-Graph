import { ref } from "vue";
import { useRouter } from "vue-router";
import { message } from "ant-design-vue";
import { generateTripPlan, generateTripPlanStream } from "@/services/api";
import type {
  TripFormData,
  SessionResponse,
  ThinkingStep,
  SSEPlanEvent,
  SSEExecuteEvent,
  SSEExecuteStartEvent,
  SSEExecuteEndEvent,
  SSESummarizeStartEvent,
  SSESummarizeProgressEvent,
  SSESummarizeEndEvent,
  SSESummarizeEvent,
  SSEReviewEvent,
} from "@/types";

export function useTripSubmit() {
  const router = useRouter();
  const loading = ref(false);
  const loadingProgress = ref(0);
  const loadingStatus = ref("");
  const thinkingSteps = ref<ThinkingStep[]>([]);
  const isThinkingRunning = ref(false);
  const hasThinkingError = ref(false);
  const useStreamMode = ref(true);

  const addThinkingStep = (
    node: string,
    display_name: string,
    icon: string,
    msg: string,
    status: ThinkingStep["status"],
    details?: string,
    plan_items?: any[],
  ) => {
    thinkingSteps.value.push({
      id: `${node}-${Date.now()}`,
      node,
      display_name,
      icon,
      message: msg,
      status,
      timestamp: Date.now(),
      details,
      plan_items,
    });
  };

  const completeCurrentStep = () => {
    const lastStep = thinkingSteps.value[thinkingSteps.value.length - 1];
    if (lastStep && lastStep.status === "running") {
      lastStep.status = "completed";
    }
  };

  const handleSubmitStream = async (requestData: TripFormData) => {
    try {
      await generateTripPlanStream(requestData, {
        onStart: (data) => {
          loadingStatus.value = data.message;
          addThinkingStep("start", "开始", "🚀", data.message, "running");
        },
        onPlan: (data: SSEPlanEvent) => {
          loadingStatus.value = data.message;
          completeCurrentStep();
          addThinkingStep(
            data.node,
            data.display_name,
            data.icon,
            data.message,
            "running",
            undefined,
            data.plan_items,
          );
        },
        onExecuteStart: (data: SSEExecuteStartEvent) => {
          loadingStatus.value = data.message;
          addThinkingStep(
            `execute-${data.task_type}-${Date.now()}`,
            data.is_parallel
              ? `⚡ ${data.task_type_display}`
              : data.task_type_display,
            data.task_icon,
            data.message,
            "running",
          );
        },
        onExecuteEnd: (data: SSEExecuteEndEvent) => {
          const stepIndex = thinkingSteps.value.findIndex(
            (s) =>
              s.status === "running" &&
              s.node.startsWith("execute-") &&
              s.message.includes(data.task_name),
          );
          if (stepIndex !== -1) {
            const step = thinkingSteps.value[stepIndex];
            step.status = data.status === "completed" ? "completed" : "failed";
            step.message = data.message;
            if (data.error) step.details = data.error;
          } else {
            addThinkingStep(
              `execute-${data.task_type}-${Date.now()}`,
              data.task_type_display,
              data.task_icon,
              data.message,
              data.status === "completed" ? "completed" : "failed",
              data.error,
            );
          }
          loadingProgress.value = Math.min(85, loadingProgress.value + 8);
        },
        onExecute: (data: SSEExecuteEvent) => {
          loadingStatus.value = data.message;
          const hasRunningExecute = thinkingSteps.value.some(
            (s) => s.status === "running" && s.node.startsWith("execute-"),
          );
          if (hasRunningExecute) {
            thinkingSteps.value
              .filter(
                (s) => s.status === "running" && s.node.startsWith("execute-"),
              )
              .forEach((s) => {
                s.status = "completed";
              });
          }
          addThinkingStep(
            data.node,
            data.display_name,
            data.icon,
            data.message,
            "completed",
          );
          loadingProgress.value = Math.min(90, loadingProgress.value + 5);
        },
        onSummarizeStart: (data: SSESummarizeStartEvent) => {
          loadingStatus.value = data.message;
          completeCurrentStep();
          addThinkingStep(
            "summarize",
            "生成旅行规划",
            "📋",
            data.message,
            "running",
          );
          loadingProgress.value = 90;
        },
        onSummarizeProgress: (data: SSESummarizeProgressEvent) => {
          loadingStatus.value = data.message;
          const lastStep = thinkingSteps.value[thinkingSteps.value.length - 1];
          if (
            lastStep &&
            lastStep.node === "summarize" &&
            lastStep.status === "running"
          ) {
            lastStep.message = data.message;
          }
        },
        onSummarizeEnd: (data: SSESummarizeEndEvent) => {
          const lastStep = thinkingSteps.value[thinkingSteps.value.length - 1];
          if (
            lastStep &&
            lastStep.node === "summarize" &&
            lastStep.status === "running"
          ) {
            lastStep.status =
              data.status === "completed" ? "completed" : "failed";
            lastStep.message = data.message;
          }
        },
        onSummarize: (data: SSESummarizeEvent) => {
          loadingStatus.value = data.message;
          const existingSummarize = thinkingSteps.value.find(
            (s) => s.node === "summarize",
          );
          if (existingSummarize) {
            existingSummarize.status = "completed";
            existingSummarize.message = data.message;
          } else {
            addThinkingStep(
              data.node,
              data.display_name,
              data.icon,
              data.message,
              "completed",
            );
          }
          loadingProgress.value = 95;
          if (data.trip_plan) {
            sessionStorage.setItem("tripPlan", JSON.stringify(data.trip_plan));
          }
        },
        onReview: (data: SSEReviewEvent) => {
          completeCurrentStep();
          isThinkingRunning.value = false;
          loadingProgress.value = 100;
          loadingStatus.value = "等待用户审阅";
          if (data.trip_plan) {
            sessionStorage.setItem("tripPlan", JSON.stringify(data.trip_plan));
          }
          sessionStorage.setItem("needsReview", "true");
          message.success("旅行计划已生成，请审阅！");
          setTimeout(() => {
            loading.value = false;
            router.push("/result");
          }, 800);
        },
        onDone: (data) => {
          completeCurrentStep();
          isThinkingRunning.value = false;
          loadingProgress.value = 100;
          loadingStatus.value = data.message;
          message.success("旅行计划生成成功!");
          if (!sessionStorage.getItem("needsReview")) {
            setTimeout(() => {
              loading.value = false;
              router.push("/result");
            }, 800);
          } else {
            loading.value = false;
          }
        },
        onError: (data) => {
          hasThinkingError.value = true;
          isThinkingRunning.value = false;
          const lastStep = thinkingSteps.value[thinkingSteps.value.length - 1];
          if (lastStep && lastStep.status === "running") {
            lastStep.status = "failed";
            lastStep.message = data.message;
          } else {
            addThinkingStep("error", "错误", "❌", data.message, "failed");
          }
          message.error(data.message || "生成旅行计划失败");
          setTimeout(() => {
            loading.value = false;
            loadingProgress.value = 0;
            loadingStatus.value = "";
          }, 2000);
        },
      });
    } catch (error: any) {
      hasThinkingError.value = true;
      isThinkingRunning.value = false;
      message.error(error.message || "流式请求失败");
      setTimeout(() => {
        loading.value = false;
      }, 1000);
    }
  };

  const handleSubmitNonStream = async (
    requestData: TripFormData,
    session: SessionResponse,
  ) => {
    const progressInterval = setInterval(() => {
      if (loadingProgress.value < 90) {
        loadingProgress.value += 10;
        if (loadingProgress.value <= 30) {
          loadingStatus.value = "🔍 正在搜索景点...";
        } else if (loadingProgress.value <= 50) {
          loadingStatus.value = "🌤️ 正在查询天气...";
        } else if (loadingProgress.value <= 70) {
          loadingStatus.value = "🏨 正在推荐酒店...";
        } else {
          loadingStatus.value = "📋 正在生成行程计划...";
        }
      }
    }, 500);

    try {
      const response = await generateTripPlan(
        requestData,
        session.token.access_token,
      );

      clearInterval(progressInterval);
      loadingProgress.value = 100;
      loadingStatus.value = "✅ 完成!";

      if (response.success && response.data) {
        sessionStorage.setItem("tripPlan", JSON.stringify(response.data));
        message.success("旅行计划生成成功!");
        setTimeout(() => {
          loading.value = false;
          router.push("/result");
        }, 500);
      } else {
        message.error(response.message || "生成失败");
        loading.value = false;
      }
    } catch (error: any) {
      clearInterval(progressInterval);
      message.error(error.message || "生成旅行计划失败，请稍后重试");
      loading.value = false;
    }
  };

  const startSubmit = async (
    requestData: TripFormData,
    session: SessionResponse,
  ) => {
    loading.value = true;
    loadingProgress.value = 0;
    loadingStatus.value = "正在初始化...";
    thinkingSteps.value = [];
    isThinkingRunning.value = true;
    hasThinkingError.value = false;

    if (useStreamMode.value) {
      await handleSubmitStream(requestData);
    } else {
      await handleSubmitNonStream(requestData, session);
    }
  };

  const resetSubmitState = () => {
    loading.value = false;
    loadingProgress.value = 0;
    loadingStatus.value = "";
    thinkingSteps.value = [];
    isThinkingRunning.value = false;
    hasThinkingError.value = false;
  };

  return {
    loading,
    loadingProgress,
    loadingStatus,
    thinkingSteps,
    isThinkingRunning,
    hasThinkingError,
    useStreamMode,
    startSubmit,
    resetSubmitState,
  };
}
