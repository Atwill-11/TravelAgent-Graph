<template>
  <div class="form-section">
    <div class="section-header">
      <span class="section-icon">{{ icon }}</span>
      <span class="section-title">{{ title }}</span>
    </div>
    <slot></slot>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  icon: string;
  title: string;
}>();
</script>

<style scoped>
.form-section {
  margin-bottom: 32px;
  padding: 28px 32px;
  background: linear-gradient(135deg, #fafbfc 0%, #ffffff 100%);
  border-radius: 20px;
  border: 2px solid #e8ecf0;
  transition: all 0.3s ease;
  position: relative;
  overflow: hidden;
}

.form-section::before {
  content: "";
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 4px;
  background: linear-gradient(90deg, #667eea 0%, #764ba2 50%, #f093fb 100%);
  opacity: 0;
  transition: opacity 0.3s ease;
}

.form-section:hover {
  box-shadow: 0 12px 32px rgba(102, 126, 234, 0.15),
    0 4px 12px rgba(0, 0, 0, 0.08);
  transform: translateY(-3px);
  border-color: rgba(102, 126, 234, 0.3);
}

.form-section:hover::before {
  opacity: 1;
}

.section-header {
  display: flex;
  align-items: center;
  margin-bottom: 24px;
  padding-bottom: 16px;
  border-bottom: 3px solid;
  border-image: linear-gradient(90deg, #667eea 0%, #764ba2 100%) 1;
  position: relative;
}

.section-header::after {
  content: "";
  position: absolute;
  bottom: -3px;
  left: 0;
  width: 60px;
  height: 3px;
  background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
}

.section-icon {
  font-size: 28px;
  margin-right: 14px;
  filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.1));
}

.section-title {
  font-size: 20px;
  font-weight: 700;
  color: #333;
  letter-spacing: 0.5px;
}
</style>
