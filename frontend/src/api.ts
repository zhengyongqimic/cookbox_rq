import { axiosInstance } from './context/AuthContext';

export const uploadVideo = async (file: File) => {
  const formData = new FormData();
  formData.append('video', file);

  const processingResponse = await axiosInstance.post('/upload', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });
  
  return processingResponse.data;
};

export const analyzeVideoLink = async (url: string) => {
  const response = await axiosInstance.post('/analyze-link', { url });
  return response.data;
};

export const getRecipes = async () => {
  const response = await axiosInstance.get('/recipes');
  return response.data;
};

export const createRecipe = async (data: { title: string; description: string; video_id: string }) => {
  const response = await axiosInstance.post('/recipes', data);
  return response.data;
};

export const getVideoStatus = async (fileId: string) => {
  const response = await axiosInstance.get(`/status/${fileId}`);
  return response.data;
};
