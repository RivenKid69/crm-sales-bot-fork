import { SetMetadata } from '@nestjs/common';

export const Provider = (provider: string) => SetMetadata('provider', provider);
