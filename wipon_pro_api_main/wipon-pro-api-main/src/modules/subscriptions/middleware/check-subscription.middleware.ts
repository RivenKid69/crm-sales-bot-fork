// import { Injectable, NestMiddleware } from '@nestjs/common';
// import { Request, Response, NextFunction } from 'express';
// import { ErrorPresenter } from 'src/common/presenters/error.presenter';
// import { StatusesEnum } from 'src/common/enums/statuses.enum';
// import { SubscriptionUseCases } from '../subscriptions.use-cases';
//
// @Injectable()
// export class CheckSubscriptionMiddleware implements NestMiddleware {
//   constructor(private subscriptionUseCases: SubscriptionUseCases) {}
//
//   async use(req: Request, res: Response, next: NextFunction) {
//     const subscriptions = await this.subscriptionUseCases.findActiveSubscriptionOfUser(this.auth.getUser());
//
//     if (subscriptions) {
//       if (subscriptions.updated_at.getTime() > Date.now() || subscriptions.expires_at.getTime() < Date.now()) {
//         return res.json({
//           error: await this.i18n.translate('subscriptions.NO_ACTIVE_SUBSCRIPTION'),
//           status: StatusesEnum.Error,
//         } as ErrorPresenter);
//       }
//     }
//     next();
//   }
// }
