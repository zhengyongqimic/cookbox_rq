import React from 'react';
import { PlayCircle, Clock } from 'lucide-react';
import type { Recipe } from '../types';

interface RecipeCardProps {
  recipe: Recipe;
  onClick: () => void;
}

const RecipeCard: React.FC<RecipeCardProps> = ({ recipe, onClick }) => {
  const [thumbnailFailed, setThumbnailFailed] = React.useState(false);
  const durationLabel = recipe.duration_seconds
    ? `${Math.floor(recipe.duration_seconds / 60)}:${Math.floor(recipe.duration_seconds % 60).toString().padStart(2, '0')}`
    : null;

  return (
    <div 
      className="bg-zinc-800 rounded-xl overflow-hidden shadow-lg hover:shadow-orange-500/10 transition-all hover:-translate-y-1 cursor-pointer border border-zinc-700 hover:border-orange-500/50 group"
      onClick={onClick}
    >
      <div className="relative aspect-video bg-zinc-900 flex items-center justify-center overflow-hidden">
        {recipe.thumbnail_url && !thumbnailFailed ? (
          <img
            src={recipe.thumbnail_url}
            alt={recipe.title}
            className="absolute inset-0 h-full w-full object-cover transition-transform duration-500 group-hover:scale-105"
            onError={() => setThumbnailFailed(true)}
          />
        ) : (
          <div className="absolute inset-0 bg-zinc-800 opacity-70 group-hover:scale-105 transition-transform duration-500" />
        )}
        <div className="absolute inset-0 bg-gradient-to-t from-black/80 to-transparent z-10" />
        <PlayCircle size={48} className="text-zinc-600 group-hover:text-orange-500 transition-colors z-20" />
        {durationLabel && (
          <div className="absolute bottom-3 right-3 z-20 rounded bg-black/70 px-2 py-1 text-xs text-white">
            {durationLabel}
          </div>
        )}
      </div>
      
      <div className="p-4">
        <h3 className="text-xl font-bold text-white mb-2 line-clamp-1 group-hover:text-orange-500 transition-colors">
          {recipe.title}
        </h3>
        <p className="text-zinc-400 text-sm line-clamp-2 mb-4 h-10">
          {recipe.description || "No description provided."}
        </p>
        
        <div className="flex items-center justify-between text-xs text-zinc-500 border-t border-zinc-700/50 pt-3">
            <span className="flex items-center gap-1">
                <Clock size={12} />
                {new Date(recipe.created_at).toLocaleDateString()}
            </span>
            <span className="bg-zinc-900 px-2 py-1 rounded text-zinc-400 group-hover:text-orange-400 transition-colors">
                Watch Recipe
            </span>
        </div>
      </div>
    </div>
  );
};

export default RecipeCard;
