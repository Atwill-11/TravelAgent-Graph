import { reactive, watch } from "vue";
import { message } from "ant-design-vue";
import type { TripFormData } from "@/types";
import type { Dayjs } from "dayjs";

export type HomeFormData = Omit<TripFormData, "start_date" | "end_date"> & {
  start_date: Dayjs | null;
  end_date: Dayjs | null;
};

export function useTripForm() {
  const formData = reactive<HomeFormData>({
    city: "",
    start_date: null,
    end_date: null,
    travel_days: 1,
    transportation: "公共交通",
    accommodation: "经济型酒店",
    preferences: [],
    free_text_input: "",
  });

  watch(
    [() => formData.start_date, () => formData.end_date],
    ([start, end]) => {
      if (start && end) {
        const days = end.diff(start, "day") + 1;
        if (days > 0 && days <= 30) {
          formData.travel_days = days;
        } else if (days > 30) {
          message.warning("旅行天数不能超过30天");
          formData.end_date = null;
        } else {
          message.warning("结束日期不能早于开始日期");
          formData.end_date = null;
        }
      }
    },
  );

  const getRequestData = (): TripFormData | null => {
    if (!formData.start_date || !formData.end_date) {
      message.error("请选择日期");
      return null;
    }
    return {
      city: formData.city,
      start_date: formData.start_date.format("YYYY-MM-DD"),
      end_date: formData.end_date.format("YYYY-MM-DD"),
      travel_days: formData.travel_days,
      transportation: formData.transportation,
      accommodation: formData.accommodation,
      preferences: formData.preferences,
      free_text_input: formData.free_text_input,
    };
  };

  const resetForm = () => {
    formData.city = "";
    formData.start_date = null;
    formData.end_date = null;
    formData.travel_days = 1;
    formData.transportation = "公共交通";
    formData.accommodation = "经济型酒店";
    formData.preferences = [];
    formData.free_text_input = "";
  };

  return {
    formData,
    getRequestData,
    resetForm,
  };
}
