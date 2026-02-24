import {
  CACHE_MANAGER,
  CanActivate,
  ExecutionContext,
  Inject,
  Injectable,
  UnauthorizedException,
} from '@nestjs/common';
import { Observable } from 'rxjs';
import { Cache } from 'cache-manager';
import rateLimitsConfig from '../../config/rate-limits.config';
import { getDiffInSecsTillTomorrow } from '../helpers/datetime';
import { DoomguyService } from '../services/doomguy/doomguy.service';
import { UserDao } from '../dao/user.dao';

@Injectable()
export class UserRateLimitGuard implements CanActivate {
  constructor(@Inject(CACHE_MANAGER) private cacheManager: Cache, private doomguyService: DoomguyService) {}

  canActivate(context: ExecutionContext): boolean | Promise<boolean> | Observable<boolean> {
    const req = context.switchToHttp().getRequest();
    if (!req.user) throw new UnauthorizedException();
    return this.validateUserRate(req.user);
  }

  private async validateUserRate(user: UserDao): Promise<boolean> {
    const counterKey = rateLimitsConfig.user.counter_key_prefix + user.id;
    const flagKey = rateLimitsConfig.user.exceeding_flag_prefix + user.id;
    let counter = await this.cacheManager.get(counterKey);
    if (counter === null) counter = 0;
    await this.cacheManager.set(counterKey, counter, { ttl: getDiffInSecsTillTomorrow() });

    let counterNum = await this.cacheManager.get(counterKey);
    counterNum = counterNum ? counterNum : 0;
    const hasFlag = await this.cacheManager.get(flagKey);

    // eslint-disable-next-line @typescript-eslint/ban-ts-comment
    // @ts-ignore
    if (counterNum > rateLimitsConfig.user.limit && !hasFlag) {
      const msg = `Пользователь ${user.phone_number} за сегодняшний день сделал более ${rateLimitsConfig.user.limit} запросов`;
      await this.doomguyService.commitRage(msg, '', '9');
      await this.cacheManager.set(flagKey, true, { ttl: getDiffInSecsTillTomorrow() });
    }
    return true;
  }
}
