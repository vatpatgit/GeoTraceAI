import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'
import type { AnalyticsAnswer } from '@/lib/api'
import { useAppStore } from '@/store/useAppStore'
import AnswerCard from './AnswerCard'

const answer: AnalyticsAnswer = {
  question: 'q', interpreted_as: {}, operation: 'largest_changes', understood: true, data: {}, answer: 'Top 2 detections by area.',
  answer_source: 'deterministic', measured_facts: ['#1: 72.0 ha'], caveats: ['Severity is a heuristic tier, not a probability.'], suggestions: [],
  references: [{ kind: 'feature', id: 'f-1', label: '#1 vegetation decrease (72 ha)', centroid: [-62.3, -10.9], analysis_id: 'a-1' }],
}

beforeEach(() => useAppStore.setState({ selectedFeatureId: null, activeAnalysisId: null, analyses: [], flyRequest: null }))

describe('AnswerCard', () => {
  it('shows the statement, measured facts and caveats', () => {
    render(<AnswerCard answer={answer} />)
    expect(screen.getByText('Top 2 detections by area.')).toBeInTheDocument()
    expect(screen.getByText('#1: 72.0 ha')).toBeInTheDocument()
    expect(screen.getByText(/not a probability/)).toBeInTheDocument()
  })
  it('a feature reference selects the detection and flies to it', async () => {
    render(<AnswerCard answer={answer} />)
    await userEvent.click(screen.getByRole('button', { name: /#1 vegetation decrease/ }))
    const s = useAppStore.getState()
    expect(s.selectedFeatureId).toBe('f-1')
    expect(s.activeAnalysisId).toBe('a-1')
    expect(s.flyRequest?.center).toEqual([-62.3, -10.9])
  })
})
