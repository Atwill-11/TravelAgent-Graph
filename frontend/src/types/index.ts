export interface Location {
  longitude: number
  latitude: number
}

export interface Attraction {
  name: string
  address: string
  location: Location
  poi_id?: string
  city?: string
  type?: string
  rating?: number
  open_time?: string
  opentime2?: string
  business_area?: string
  level?: string
  ticket_price?: number
  visit_duration: number
  description?: string
  photos?: string[]
  image_url?: string
}

export interface Meal {
  type: string
  name: string
  address?: string
  location?: Location
  description?: string
  estimated_cost?: number
}

export interface Hotel {
  name: string
  poi_id?: string
  address: string
  location?: Location
  business_area?: string
  city?: string
  rating?: number
  hotel_type?: string
  hotel_ordering?: number
  lowest_price?: number
  distance: string
}

export interface Budget {
  total_attractions: number
  total_hotels: number
  total_meals: number
  total_transportation: number
  total: number
}

export interface DayPlan {
  date: string
  day_index: number
  description: string
  transportation: string
  accommodation: string
  hotel?: Hotel
  attractions: Attraction[]
  meals: Meal[]
}

export interface LocationInfo {
  name: string
  id: string
  lat: string
  lon: string
  adm2: string
  adm1: string
  country: string
}

export interface QWeatherInfo {
  date: string
  temp_max: string
  temp_min: string
  text_day: string
  text_night: string
  wind_dir: string
  wind_scale: string
  humidity: string
  precip: string
  uv_index: string
  vis: string
  sunrise: string
  sunset: string
}

export interface AirQualityInfo {
  aqi: number
  category: string
  primary_pollutant: string
  pm25: number
  pm10: number
  health_advice: string
}

export interface TravelWeatherData {
  location: LocationInfo
  weather: QWeatherInfo[]
  air_quality?: AirQualityInfo
  travel_advice: string
}

export interface TripPlan {
  city: string
  start_date: string
  end_date: string
  days: DayPlan[]
  weather_info?: TravelWeatherData
  overall_suggestions: string
  budget?: Budget
}

export interface TripFormData {
  city: string
  start_date: string
  end_date: string
  travel_days: number
  transportation: string
  accommodation: string
  preferences: string[]
  free_text_input: string
}

export interface TripPlanResponse {
  success: boolean
  message: string
  data?: TripPlan
}

export interface TokenData {
  access_token: string
  token_type: string
  expires_at: string
}

export interface LoginResponse {
  access_token: string
  token_type: string
  expires_at: string
}

export interface SessionResponse {
  session_id: string
  name: string
  token: TokenData
}

export interface UserResponse {
  id: number
  email: string
  token: TokenData
}

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system'
  content: string
}

export interface ChatResponse {
  messages: ChatMessage[]
}

export interface StreamResponse {
  content: string
  done: boolean
}

export interface SSEPlanItem {
  task: string
  type: string
  type_display: string
  icon: string
}

export interface SSEStepEvent {
  node: string
  display_name: string
  icon: string
  message: string
}

export interface SSEPlanEvent extends SSEStepEvent {
  plan_items: SSEPlanItem[]
  messages: string[]
}

export interface SSEExecuteEvent extends SSEStepEvent {
  current_task: string | null
  task_type: string | null
  task_type_display: string
  task_icon: string
  task_status: string | null
  messages: string[]
}

export interface SSESummarizeEvent extends SSEStepEvent {
  trip_plan: TripPlan | null
  suggestions: string
  messages: string[]
}

export interface SSEReviewEvent extends SSEStepEvent {
  trip_plan: TripPlan | null
  messages: string[]
  user_decision: string
}

export interface SSEResumeRequest {
  action: 'complete' | 'modify'
  feedback?: string
}

export interface SSEDoneEvent {
  message: string
  success: boolean
}

export interface SSEErrorEvent {
  message: string
  success: boolean
}

export interface SSEStartEvent {
  message: string
  session_id: string
}

export interface ThinkingStep {
  id: string
  node: string
  display_name: string
  icon: string
  message: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  timestamp: number
  details?: string
  plan_items?: SSEPlanItem[]
}
