'use client'

import { Play, Pause, SkipBack, SkipForward, Clock } from 'lucide-react'
import { useEffect, useRef } from 'react'
import { useAppStore } from '@/store/useAppStore'
import { format, parseISO, addDays, differenceInDays, isBefore, isAfter } from 'date-fns'

export default function TimeSlider() {
  const {
    mapView,
    setCurrentDate,
    isPlaying,
    setIsPlaying,
  } = useAppStore()

  const intervalRef = useRef<NodeJS.Timeout | null>(null)

  const startDate = parseISO(mapView.dateRange.start)
  const endDate = parseISO(mapView.dateRange.end)
  const currentDate = parseISO(mapView.currentDate)
  const totalDays = Math.max(1, differenceInDays(endDate, startDate) + 1)
  const currentDay = Math.max(0, differenceInDays(currentDate, startDate))

  // Auto-play animation
  useEffect(() => {
    if (isPlaying) {
      intervalRef.current = setInterval(() => {
        const nextDate = addDays(currentDate, 1)
        if (isAfter(nextDate, endDate)) {
          setIsPlaying(false)
          setCurrentDate(mapView.dateRange.start)
        } else {
          setCurrentDate(format(nextDate, 'yyyy-MM-dd'))
        }
      }, 400)
    } else {
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
        intervalRef.current = null
      }
    }

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
      }
    }
  }, [isPlaying, currentDate, endDate, mapView.dateRange.start, setCurrentDate, setIsPlaying])

  const handleSliderChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const day = parseInt(e.target.value)
    const newDate = addDays(startDate, day)
    setCurrentDate(format(newDate, 'yyyy-MM-dd'))
  }

  const handlePrevious = () => {
    const prevDate = addDays(currentDate, -1)
    if (isBefore(prevDate, startDate)) {
      setCurrentDate(mapView.dateRange.start)
    } else {
      setCurrentDate(format(prevDate, 'yyyy-MM-dd'))
    }
  }

  const handleNext = () => {
    const nextDate = addDays(currentDate, 1)
    if (isAfter(nextDate, endDate)) {
      setCurrentDate(mapView.dateRange.end)
    } else {
      setCurrentDate(format(nextDate, 'yyyy-MM-dd'))
    }
  }

  const progress = totalDays > 1 ? (currentDay / (totalDays - 1)) * 100 : 0

  return (
    <div className="px-5 py-3">
      <div className="flex items-center gap-4">
        {/* Current date display */}
        <div className="flex items-center gap-2.5 min-w-[150px]">
          <div className="w-6 h-6 rounded-md bg-accent/10 flex items-center justify-center">
            <Clock className="w-3 h-3 text-accent" />
          </div>
          <div>
            <div className="text-xs font-bold text-white leading-none">
              {format(currentDate, 'MMM dd, yyyy')}
            </div>
            <div className="flex items-center gap-1 mt-0.5">
              <div className="w-1 h-1 rounded-full bg-emerald-400 animate-pulse" />
              <span className="text-[9px] text-emerald-400/70 font-medium">Data synced</span>
            </div>
          </div>
        </div>

        {/* Playback Controls */}
        <div className="flex items-center gap-0.5">
          <button
            onClick={handlePrevious}
            className="p-1.5 rounded-md hover:bg-white/5 text-slate-400 hover:text-white transition-colors"
            aria-label="Previous day"
            id="timeline-prev"
          >
            <SkipBack className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={() => setIsPlaying(!isPlaying)}
            className={`p-2 rounded-lg transition-all ${
              isPlaying
                ? 'bg-accent/20 text-accent shadow-sm shadow-accent/20 ring-1 ring-accent/20'
                : 'bg-white/5 text-white hover:bg-white/10'
            }`}
            aria-label={isPlaying ? 'Pause' : 'Play'}
            id="timeline-play"
          >
            {isPlaying ? (
              <Pause className="w-3.5 h-3.5" />
            ) : (
              <Play className="w-3.5 h-3.5" />
            )}
          </button>
          <button
            onClick={handleNext}
            className="p-1.5 rounded-md hover:bg-white/5 text-slate-400 hover:text-white transition-colors"
            aria-label="Next day"
            id="timeline-next"
          >
            <SkipForward className="w-3.5 h-3.5" />
          </button>
        </div>

        {/* Scrubber */}
        <div className="flex-1 mx-2 relative">
          {/* Progress background */}
          <div className="absolute top-1/2 -translate-y-1/2 left-0 right-0 h-1.5 bg-white/5 rounded-full overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-accent/60 to-accent rounded-full transition-all duration-200"
              style={{ width: `${progress}%` }}
            />
          </div>
          <input
            type="range"
            min="0"
            max={totalDays - 1}
            value={currentDay}
            onChange={handleSliderChange}
            className="w-full relative z-10"
            aria-label="Time scrubber"
            id="timeline-scrubber"
            style={{ background: 'transparent' }}
          />
        </div>

        {/* Day counter */}
        <div className="text-xs min-w-[70px] text-right font-mono flex items-center gap-1 justify-end">
          <span className="text-accent font-semibold">{currentDay + 1}</span>
          <span className="text-slate-600">/</span>
          <span className="text-slate-500">{totalDays}</span>
        </div>
      </div>
    </div>
  )
}
