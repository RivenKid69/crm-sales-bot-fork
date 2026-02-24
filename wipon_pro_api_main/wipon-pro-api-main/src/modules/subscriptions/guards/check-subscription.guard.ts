import { CanActivate, ExecutionContext, HttpException, Injectable, UnauthorizedException } from '@nestjs/common';
import { Observable } from 'rxjs';
import { CountUsersActiveSubscriptionUseCase } from '../domain/use-cases/count-users-active-subscription.use-case';
import { constants } from 'http2';

@Injectable()
export class CheckSubscriptionGuard implements CanActivate {
  constructor(private readonly countUsersActiveSubscription: CountUsersActiveSubscriptionUseCase) {}

  canActivate(context: ExecutionContext): boolean | Promise<boolean> | Observable<boolean> {
    const req = context.switchToHttp().getRequest();
    if (!req.user) throw new UnauthorizedException();
    return this.validateSubscription(req.user.id);
  }

  private async validateSubscription(userId: number): Promise<boolean> {
    const subscription = await this.countUsersActiveSubscription.handle(userId);
    if (!subscription) throw new HttpException('Payment Required', constants.HTTP_STATUS_PAYMENT_REQUIRED);

    return true;
  }
}
