import React, { useEffect, useState } from 'react';
import { Upload, ChefHat, Loader2, PlayCircle, Link as LinkIcon, LogOut, Plus, X, ArrowLeft } from 'lucide-react';
import type { GestureType, ProcessingStatus, Recipe, RecipeDetailPayload, Step } from '../types';
import { uploadVideo, analyzeVideoLink, getRecipes, createRecipe, getVideoStatus } from '../api';
import VideoPlayer from '../components/VideoPlayer';
import StepList from '../components/StepList';
import GestureFeedback from '../components/GestureFeedback';
import ServerLogs from '../components/ServerLogs';
import RecipeCard from '../components/RecipeCard';
import GestureCapture from '../components/GestureCapture';
import io from 'socket.io-client';
import { useAuth } from '../context/AuthContext';

const normalizeStep = (step: Step): Step => ({
  ...step,
  start: step.start ?? step.start_time ?? 0,
  end: step.end ?? step.end_time ?? 0,
});

const Dashboard = () => {
  const { logout, user } = useAuth();

  const [view, setView] = useState<'grid' | 'player' | 'overview'>('grid');
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [recipes, setRecipes] = useState<Recipe[]>([]);
  const [loadingRecipes, setLoadingRecipes] = useState(false);

  const [steps, setSteps] = useState<Step[]>([]);
  const [currentStepIndex, setCurrentStepIndex] = useState<number>(0);
  const [lastGesture, setLastGesture] = useState<GestureType>(null);
  const [gestureLogs, setGestureLogs] = useState<{ time: string; gesture: string }[]>([]);
  const [originalSource, setOriginalSource] = useState<string | null>(null);
  const [togglePlayTrigger, setTogglePlayTrigger] = useState<number>(0);
  const [playerMuted, setPlayerMuted] = useState(true);
  const [activeRecipeHasAudio, setActiveRecipeHasAudio] = useState<boolean | null>(null);

  const [file, setFile] = useState<File | null>(null);
  const [videoLink, setVideoLink] = useState('');
  const [processingStatus, setProcessingStatus] = useState<ProcessingStatus | null>(null);
  const [newRecipeData, setNewRecipeData] = useState({ title: '', description: '', video_id: '' });
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    fetchRecipes();
  }, []);

  const fetchRecipes = async () => {
    setLoadingRecipes(true);
    try {
      const data = await getRecipes();
      setRecipes(data);
    } catch (error) {
      console.error('Failed to fetch recipes', error);
    } finally {
      setLoadingRecipes(false);
    }
  };

  useEffect(() => {
    const socket = io('/', { path: '/socket.io' });

    socket.on('processing_update', (status: ProcessingStatus) => {
      if (isModalOpen) {
        setProcessingStatus(status);
        if (status.status === 'completed' && status.steps) {
          setNewRecipeData((prev) => ({ ...prev, video_id: status.file_id }));
        }
      }
    });

    socket.on('gesture_detected', (data: { gesture: GestureType }) => {
      const log = {
        time: new Date().toLocaleTimeString(),
        gesture: data.gesture || 'unknown',
      };
      setGestureLogs((prev) => [log, ...prev].slice(0, 20));
    });

    return () => {
      socket.disconnect();
    };
  }, [isModalOpen]);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
    }
  };

  const handleUpload = async () => {
    if (!file) return;
    try {
      setProcessingStatus({ file_id: '', status: 'analyzing', progress: 0 });
      await uploadVideo(file);
    } catch (error: any) {
      console.error('Upload failed', error);
      setProcessingStatus({ file_id: '', status: 'error', message: error.response?.data?.error || 'Upload failed' });
    }
  };

  const handleLinkAnalyze = async () => {
    if (!videoLink) return;
    try {
      setProcessingStatus({ file_id: '', status: 'analyzing', progress: 0 });
      await analyzeVideoLink(videoLink);
    } catch (error: any) {
      console.error('Link analysis failed', error);
      setProcessingStatus({ file_id: '', status: 'error', message: error.response?.data?.error || 'Analysis failed' });
    }
  };

  const handleSaveRecipe = async () => {
    if (!newRecipeData.title || !newRecipeData.video_id) return;
    setIsSaving(true);
    try {
      await createRecipe(newRecipeData);
      await fetchRecipes();
      closeModal();
    } catch (error) {
      console.error('Failed to save recipe', error);
    } finally {
      setIsSaving(false);
    }
  };

  const closeModal = () => {
    setIsModalOpen(false);
    setFile(null);
    setVideoLink('');
    setProcessingStatus(null);
    setNewRecipeData({ title: '', description: '', video_id: '' });
  };

  const openRecipe = async (recipe: Recipe) => {
    try {
      const status: RecipeDetailPayload = await getVideoStatus(recipe.video_id);
      if (status?.steps?.length) {
        setSteps(status.steps.map(normalizeStep));
        setOriginalSource(status.original_url || null);
        setActiveRecipeHasAudio(status.has_audio ?? recipe.has_audio ?? null);
        setCurrentStepIndex(0);
        setPlayerMuted(true);
        setView('player');
      } else {
        console.error('No steps found for this recipe');
      }
    } catch (error) {
      console.error('Failed to load recipe details', error);
    }
  };

  const handleGesture = (gesture: GestureType) => {
    if (!gesture) return;

    switch (gesture) {
      case 'next':
        if (currentStepIndex < steps.length - 1) {
          setCurrentStepIndex((prev) => prev + 1);
          setLastGesture(gesture);
        }
        break;
      case 'prev':
        if (currentStepIndex > 0) {
          setCurrentStepIndex((prev) => prev - 1);
          setLastGesture(gesture);
        }
        break;
      case 'overview':
        if (view !== 'overview') {
          setView('overview');
          setLastGesture(gesture);
        }
        break;
      case 'toggle_pause':
        if (view === 'player') {
          setTogglePlayTrigger(Date.now());
          setLastGesture('toggle_pause');
        }
        break;
      case 'open_palm':
        if (view === 'overview') {
          setView('player');
          setLastGesture('resume_overview');
        } else if (view === 'player') {
          setTogglePlayTrigger(Date.now());
          setLastGesture('toggle_pause');
        }
        break;
    }
  };

  if (view === 'overview') {
    return (
      <div className="min-h-screen bg-zinc-950 text-white p-8 flex flex-col items-center">
        <GestureCapture enabled={steps.length > 0} onGesture={handleGesture} />
        <h1 className="text-4xl font-bold mb-8 flex items-center gap-4 text-orange-500">
          <ChefHat size={40} />
          Kitchen Assistant - Overview
        </h1>

        <StepList
          steps={steps}
          currentStepIndex={currentStepIndex}
          onStepClick={(idx) => {
            setCurrentStepIndex(idx);
            setView('player');
          }}
        />
        <button
          onClick={() => setView('player')}
          className="mt-8 px-8 py-3 bg-orange-500 text-white rounded-full font-bold hover:bg-orange-600 transition-colors"
        >
          Resume Cooking
        </button>
        <GestureFeedback gesture={lastGesture} onClear={() => setLastGesture(null)} />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-zinc-950 text-white flex flex-col items-center p-4 md:p-8 font-sans">
      <header className="w-full max-w-6xl flex justify-between items-center mb-8">
        <div className="flex items-center gap-4">
          {view === 'player' && (
            <button
              onClick={() => setView('grid')}
              className="p-2 bg-zinc-800 rounded-full hover:bg-zinc-700 transition-colors"
              title="Back to Recipes"
            >
              <ArrowLeft size={20} />
            </button>
          )}
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <ChefHat className="text-orange-500" />
            HyperKitchen
          </h1>
        </div>

        <div className="flex items-center gap-4">
          <span className="text-zinc-400 hidden md:inline">Welcome, {user?.username}</span>
          <button onClick={logout} className="text-zinc-400 hover:text-white transition-colors" title="Logout">
            <LogOut size={20} />
          </button>
        </div>
      </header>

      <main className="w-full max-w-6xl flex flex-col gap-8 relative">
        {view === 'grid' ? (
          <>
            <div className="flex justify-between items-center">
              <h2 className="text-2xl font-bold text-white">My Recipes</h2>
              <button
                onClick={() => setIsModalOpen(true)}
                className="flex items-center gap-2 bg-orange-500 hover:bg-orange-600 text-white px-4 py-2 rounded-lg font-bold transition-all shadow-lg shadow-orange-500/20"
              >
                <Plus size={20} />
                Add Recipe
              </button>
            </div>

            {loadingRecipes ? (
              <div className="flex justify-center py-20">
                <Loader2 className="animate-spin text-orange-500" size={40} />
              </div>
            ) : recipes.length === 0 ? (
              <div className="text-center py-20 text-zinc-500">
                <p className="text-xl mb-4">No recipes found.</p>
                <p>Click "Add Recipe" to upload your first cooking video!</p>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {recipes.map((recipe) => (
                  <RecipeCard key={recipe.id} recipe={recipe} onClick={() => openRecipe(recipe)} />
                ))}
              </div>
            )}
          </>
        ) : (
          <div className="w-full flex flex-col items-center gap-8">
            <GestureCapture enabled={steps.length > 0} onGesture={handleGesture} />
            {steps.length > 0 && (
              <div className="text-sm text-zinc-400 self-start">
                Step {currentStepIndex + 1} of {steps.length}
              </div>
            )}

            <VideoPlayer
              currentStep={steps[currentStepIndex]}
              onGesture={handleGesture}
              originalSource={originalSource}
              togglePlayTrigger={togglePlayTrigger}
              isMuted={playerMuted}
              onMutedChange={setPlayerMuted}
              hasAudio={activeRecipeHasAudio}
            />

            <StepList
              steps={steps}
              currentStepIndex={currentStepIndex}
              onStepClick={setCurrentStepIndex}
            />

            <div className="w-full max-w-4xl bg-zinc-900/50 p-6 rounded-xl border border-zinc-800">
              <h3 className="text-lg font-bold mb-4 text-zinc-300">Gesture Controls</h3>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div className="flex flex-col items-center gap-2 p-3 bg-black/40 rounded-lg">
                  <div className="text-xl">Left</div>
                  <div className="font-bold text-orange-500">Prev Step</div>
                  <div className="text-xs text-zinc-500 text-center">Point Left</div>
                </div>
                <div className="flex flex-col items-center gap-2 p-3 bg-black/40 rounded-lg">
                  <div className="text-xl">Right</div>
                  <div className="font-bold text-orange-500">Next Step</div>
                  <div className="text-xs text-zinc-500 text-center">Point Right</div>
                </div>
                <div className="flex flex-col items-center gap-2 p-3 bg-black/40 rounded-lg">
                  <div className="text-xl">Palm</div>
                  <div className="font-bold text-orange-500">Pause / Play</div>
                  <div className="text-xs text-zinc-500 text-center">Open Palm</div>
                </div>
                <div className="flex flex-col items-center gap-2 p-3 bg-black/40 rounded-lg">
                  <div className="text-xl">Both</div>
                  <div className="font-bold text-orange-500">Overview</div>
                  <div className="text-xs text-zinc-500 text-center">Both Hands Up</div>
                </div>
              </div>
            </div>
          </div>
        )}
      </main>

      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
          <div className="bg-zinc-900 w-full max-w-2xl rounded-2xl border border-zinc-800 shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
            <div className="flex justify-between items-center p-6 border-b border-zinc-800">
              <h3 className="text-xl font-bold text-white">Add New Recipe</h3>
              <button onClick={closeModal} className="text-zinc-400 hover:text-white transition-colors">
                <X size={24} />
              </button>
            </div>

            <div className="p-6 overflow-y-auto">
              {processingStatus?.status === 'completed' ? (
                <div className="space-y-6">
                  <div className="bg-green-500/10 border border-green-500/20 text-green-500 p-4 rounded-lg flex items-center gap-3">
                    <div className="bg-green-500 rounded-full p-1">
                      <ChefHat size={16} className="text-black" />
                    </div>
                    <div>
                      <p className="font-bold">Analysis Complete!</p>
                      <p className="text-sm opacity-80">{processingStatus.steps?.length} steps generated.</p>
                    </div>
                  </div>

                  {processingStatus.thumbnail_url && (
                    <img
                      src={processingStatus.thumbnail_url}
                      alt="Recipe thumbnail"
                      className="w-full aspect-video object-cover rounded-xl border border-zinc-800"
                    />
                  )}

                  <div>
                    <label className="block text-sm font-medium text-zinc-400 mb-1">Recipe Title</label>
                    <input
                      type="text"
                      value={newRecipeData.title}
                      onChange={(e) => setNewRecipeData((prev) => ({ ...prev, title: e.target.value }))}
                      placeholder="e.g. Spicy Garlic Shrimp"
                      className="w-full bg-zinc-800 border border-zinc-700 rounded-lg py-3 px-4 text-white focus:outline-none focus:border-orange-500 transition-colors"
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-zinc-400 mb-1">Description (Optional)</label>
                    <textarea
                      value={newRecipeData.description}
                      onChange={(e) => setNewRecipeData((prev) => ({ ...prev, description: e.target.value }))}
                      placeholder="Brief description of the dish..."
                      rows={3}
                      className="w-full bg-zinc-800 border border-zinc-700 rounded-lg py-3 px-4 text-white focus:outline-none focus:border-orange-500 transition-colors resize-none"
                    />
                  </div>

                  <button
                    onClick={handleSaveRecipe}
                    disabled={!newRecipeData.title || isSaving}
                    className="w-full bg-orange-500 hover:bg-orange-600 text-white font-bold py-3 rounded-lg transition-colors flex items-center justify-center disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {isSaving ? <Loader2 className="animate-spin" /> : 'Save to Cookbook'}
                  </button>
                </div>
              ) : (
                <div className="space-y-6">
                  <div className="border-2 border-dashed border-zinc-700 rounded-xl p-8 flex flex-col items-center justify-center text-center hover:bg-zinc-800/50 transition-colors">
                    <input
                      type="file"
                      accept="video/*"
                      onChange={handleFileChange}
                      className="hidden"
                      id="modal-video-upload"
                    />
                    <label htmlFor="modal-video-upload" className="cursor-pointer w-full flex flex-col items-center">
                      <div className="w-16 h-16 bg-zinc-800 rounded-full flex items-center justify-center mb-4">
                        <Upload size={24} className="text-zinc-400" />
                      </div>
                      <p className="text-lg font-medium text-zinc-200 mb-1">
                        {file ? file.name : 'Click to upload video'}
                      </p>
                      <p className="text-sm text-zinc-500">MP4, MOV, WebM (Max 500MB)</p>
                    </label>
                  </div>

                  <div className="flex items-center gap-4">
                    <div className="h-px bg-zinc-800 flex-1"></div>
                    <span className="text-zinc-500 text-sm">OR</span>
                    <div className="h-px bg-zinc-800 flex-1"></div>
                  </div>

                  <div className="flex gap-2">
                    <div className="relative flex-1">
                      <LinkIcon className="absolute left-3 top-3 text-zinc-500" size={20} />
                      <input
                        type="text"
                        placeholder="Paste video URL here..."
                        value={videoLink}
                        onChange={(e) => setVideoLink(e.target.value)}
                        className="w-full bg-zinc-800 border border-zinc-700 rounded-lg py-3 pl-10 pr-4 text-white focus:outline-none focus:border-orange-500 transition-colors"
                      />
                    </div>
                  </div>

                  <div className="pt-4">
                    {videoLink ? (
                      <button
                        onClick={handleLinkAnalyze}
                        disabled={!videoLink || processingStatus?.status === 'analyzing' || processingStatus?.status === 'slicing'}
                        className="w-full bg-orange-500 hover:bg-orange-600 text-white font-bold py-3 rounded-lg transition-colors flex items-center justify-center disabled:opacity-50"
                      >
                        {processingStatus?.status === 'analyzing' || processingStatus?.status === 'slicing' ? (
                          <div className="flex items-center gap-2">
                            <Loader2 className="animate-spin" size={20} />
                            <span>Processing... {processingStatus.progress}%</span>
                          </div>
                        ) : 'Analyze Link'}
                      </button>
                    ) : (
                      <button
                        onClick={handleUpload}
                        disabled={!file || processingStatus?.status === 'analyzing' || processingStatus?.status === 'slicing'}
                        className="w-full bg-orange-500 hover:bg-orange-600 text-white font-bold py-3 rounded-lg transition-colors flex items-center justify-center disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        {processingStatus?.status === 'analyzing' || processingStatus?.status === 'slicing' ? (
                          <div className="flex items-center gap-2">
                            <Loader2 className="animate-spin" size={20} />
                            <span>Processing... {processingStatus.progress}%</span>
                          </div>
                        ) : (
                          <div className="flex items-center gap-2">
                            <PlayCircle size={20} />
                            <span>Start Analysis</span>
                          </div>
                        )}
                      </button>
                    )}
                  </div>

                  {processingStatus?.message && (
                    <div className={`text-sm text-center ${processingStatus.status === 'error' ? 'text-red-500' : 'text-zinc-400'}`}>
                      {processingStatus.message}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      <GestureFeedback gesture={lastGesture} onClear={() => setLastGesture(null)} />
      <ServerLogs />

      <div className="fixed bottom-4 right-4 w-64 max-h-48 bg-black/80 text-xs text-green-400 p-2 rounded border border-green-900 overflow-y-auto font-mono z-40 pointer-events-none opacity-50 hover:opacity-100 transition-opacity hidden">
        <div className="font-bold border-b border-green-800 mb-1 pb-1">Gesture Log</div>
        {gestureLogs.length === 0 ? (
          <div className="text-zinc-500 italic">No gestures detected yet...</div>
        ) : (
          gestureLogs.map((log, i) => <div key={i}>[{log.time}] {log.gesture}</div>)
        )}
      </div>
    </div>
  );
};

export default Dashboard;
