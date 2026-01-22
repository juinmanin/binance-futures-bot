"""신호 충돌 해결"""
from .types import Signal, ConfirmationResult, StrategySignal, SignalAction


class SignalResolver:
    """두 전략 신호 충돌 시 우선순위 부여"""
    
    def resolve(
        self, 
        larry_signal: Signal, 
        futurechart_confirmation: ConfirmationResult
    ) -> StrategySignal:
        """
        신호 충돌 해결
        
        우선순위: 퓨처차트 추세 필터 > 변동성 돌파
        - 두 신호 일치: 높은 신뢰도로 진입
        - 신호 충돌: 퓨처차트 우선, 신뢰도 낮춤
        - 한쪽만 신호: 조건부 진입 (신뢰도 중간)
        
        Args:
            larry_signal: 래리 윌리엄스 신호
            futurechart_confirmation: 퓨처차트 확인 결과
            
        Returns:
            최종 신호
        """
        # 두 신호가 모두 일치하는 경우 (최고 신뢰도)
        if larry_signal.action != SignalAction.HOLD and futurechart_confirmation.is_confirmed:
            confidence = min(
                larry_signal.confidence * futurechart_confirmation.confidence * 1.2,
                1.0
            )
            
            return StrategySignal(
                action=larry_signal.action,
                confidence=confidence,
                entry_price=None,  # 나중에 계산
                stop_loss=None,
                take_profit_1=None,
                take_profit_2=None,
                position_size=None,
                reason=f"래리 윌리엄스 + 퓨처차트 일치: {larry_signal.reason}",
                indicators={
                    **larry_signal.indicators,
                    **futurechart_confirmation.details,
                }
            )
        
        # 래리 윌리엄스만 신호 있음
        elif larry_signal.action != SignalAction.HOLD and not futurechart_confirmation.is_confirmed:
            # 퓨처차트 확인이 없으면 신뢰도 낮춤
            confidence = larry_signal.confidence * 0.6
            
            return StrategySignal(
                action=larry_signal.action,
                confidence=confidence,
                entry_price=None,
                stop_loss=None,
                take_profit_1=None,
                take_profit_2=None,
                position_size=None,
                reason=f"래리 윌리엄스만 신호: {larry_signal.reason} (퓨처차트 미확인)",
                indicators={
                    **larry_signal.indicators,
                    **futurechart_confirmation.details,
                }
            )
        
        # 퓨처차트만 확인됨 (래리 윌리엄스 신호 없음)
        elif larry_signal.action == SignalAction.HOLD and futurechart_confirmation.is_confirmed:
            # 퓨처차트에서 추세 방향 파악
            layer1_details = futurechart_confirmation.details.get('layer1', {})
            river_direction = layer1_details.get('river_direction', 'NEUTRAL')
            
            if river_direction == 'UP':
                action = SignalAction.BUY
            elif river_direction == 'DOWN':
                action = SignalAction.SELL
            else:
                action = SignalAction.HOLD
            
            confidence = futurechart_confirmation.confidence * 0.7
            
            return StrategySignal(
                action=action,
                confidence=confidence,
                entry_price=None,
                stop_loss=None,
                take_profit_1=None,
                take_profit_2=None,
                position_size=None,
                reason=f"퓨처차트만 확인: {river_direction} 추세",
                indicators={
                    **larry_signal.indicators,
                    **futurechart_confirmation.details,
                }
            )
        
        # 둘 다 신호 없음
        else:
            return StrategySignal(
                action=SignalAction.HOLD,
                confidence=0.0,
                entry_price=None,
                stop_loss=None,
                take_profit_1=None,
                take_profit_2=None,
                position_size=None,
                reason="신호 없음",
                indicators={
                    **larry_signal.indicators,
                    **futurechart_confirmation.details,
                }
            )
