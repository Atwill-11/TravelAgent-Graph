<template>
  <a-card id="map" title="📍 景点地图" :bordered="false" class="map-card">
    <div id="amap-container" style="width: 100%; height: 100%"></div>
  </a-card>
</template>

<script setup lang="ts">
import { onMounted, onBeforeUnmount, watch, nextTick } from "vue";
import { message } from "ant-design-vue";
import AMapLoader from "@amap/amap-jsapi-loader";
import type { TripPlan } from "@/types";

const props = defineProps<{
  tripPlan: TripPlan | null;
}>();

let map: any = null;
let AMapRef: any = null;
let mapMarkers: any[] = [];
let mapPolylines: any[] = [];

onMounted(async () => {
  await nextTick();
  initMap();
});

onBeforeUnmount(() => {
  if (map) {
    map.destroy();
    map = null;
  }
});

watch(
  () => props.tripPlan,
  async (newPlan) => {
    if (newPlan && map && AMapRef) {
      await nextTick();
      refreshMapMarkers();
    }
  },
);

const initMap = async () => {
  try {
    const AMap = await AMapLoader.load({
      key: import.meta.env.VITE_AMAP_WEB_JS_KEY,
      version: "2.0",
      plugins: ["AMap.Marker", "AMap.Polyline", "AMap.InfoWindow"],
    });

    AMapRef = AMap;

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

const refreshMapMarkers = () => {
  if (!map || !AMapRef) return;

  map.remove(mapMarkers);
  map.remove(mapPolylines);
  mapMarkers = [];
  mapPolylines = [];

  addAttractionMarkers(AMapRef);
};

const addAttractionMarkers = (AMap: any) => {
  if (!props.tripPlan) return;

  const newMarkers: any[] = [];
  const allAttractions: any[] = [];

  props.tripPlan.days.forEach((day, dayIndex) => {
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

    newMarkers.push(marker);
  });

  map.add(newMarkers);
  mapMarkers = newMarkers;

  if (allAttractions.length > 0) {
    map.setFitView(newMarkers);
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
  const newPolylines: any[] = [];

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
      newPolylines.push(polyline);
    },
  );

  mapPolylines = newPolylines;
};
</script>

<style scoped>
.map-card {
  border-radius: 16px;
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.08);
  transition: all 0.3s ease;
  height: 480px;
  margin-bottom: 24px;
}

.map-card :deep(.ant-card-body) {
  height: calc(100% - 57px);
  padding: 0;
}

#amap-container {
  border-radius: 0 0 12px 12px;
}

@media (max-width: 1400px) {
  .map-card {
    height: 350px;
  }
}

@media (max-width: 768px) {
  .map-card {
    height: 300px;
  }
}
</style>
