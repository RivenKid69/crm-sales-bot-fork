import { IsIn, IsOptional } from 'class-validator';
import { ApiProperty } from '@nestjs/swagger';

export class GetUsersChecksDto {
  @ApiProperty({
    type: String,
    description: 'Check types for filtering: [valid, fake, atlas]',
    required: false,
  })
  @IsOptional()
  @IsIn(['valid', 'fake', 'atlas'])
  status: string;
}
